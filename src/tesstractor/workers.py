#
# Copyright 2018-2024 Universidad Complutense de Madrid
#
# This file is part of tesstractor
#
# SPDX-License-Identifier: GPL-3.0-or-later
# License-Filename: LICENSE.txt
#

import asyncio
import datetime
import logging
import typing
import warnings

import numpy

from tesstractor.device import Device

_logger = logging.getLogger(__name__)

# Maximum number of items waiting in a queue. If a consumer
# is stuck, the oldest items are dropped
QUEUE_MAXSIZE = 1000


class Sink(typing.Protocol):
    """Destination of averaged measurements"""

    async def send(self, payload: dict) -> None: ...


def put_drop_oldest(q: asyncio.Queue, item) -> None:
    """Put item in the queue, dropping the oldest item if it is full"""
    while True:
        try:
            q.put_nowait(item)
            return
        except asyncio.QueueFull:
            dropped = q.get_nowait()
            _logger.warning("queue is full, dropping %s", dropped)


async def read_photometer(
    device: Device,
    outputs: typing.Sequence[asyncio.Queue],
    readerconf: dict,
    stop: asyncio.Event,
):
    """Read the photometer until stop is set.

    The device must be already connected. The measurements
    are sent to all the queues in outputs. None is sent at the end.
    """
    _logger.info("starting reader of %s", device.name)
    seq = 0
    internal_buffer = []

    nsamples = readerconf.get("nsamples", 5)
    tsample = readerconf.get("tsample", 1)
    local_tz = readerconf["tz"]

    def publish(payload):
        for q in outputs:
            put_drop_oldest(q, payload)

    try:
        payload_init = dict(
            name=device.name,
            model=device.model,
            mac=str(device.register_id()),
            calib=device.calibration,
            rev=1,
            cmd="id",
            tstamp=datetime.datetime.now(datetime.UTC),
            localtz=local_tz,
        )
        publish(payload_init)

        tries = 3
        while not stop.is_set():
            # Serial I/O is blocking
            msg = await asyncio.to_thread(device.read_data, tries)
            if msg is None:
                continue

            payload = dict(msg)
            payload["localtz"] = local_tz
            _logger.debug("payload is %s", payload)

            if nsamples <= 1:
                # Send the measurement as given by the device
                payload["seq"] = seq
                publish(payload)
                seq += 1
            else:
                internal_buffer.append(payload)

            # When we have enough measurements, we collapse
            if internal_buffer and len(internal_buffer) >= nsamples:
                _logger.debug("averaging %d samples", len(internal_buffer))
                res = avg_device_buffer(internal_buffer)
                res["seq"] = seq
                internal_buffer = []
                _logger.debug("buffer avg is %s", res)
                publish(res)
                seq += 1
            # Wait a little (tsample) unless stop is set
            try:
                await asyncio.wait_for(stop.wait(), timeout=tsample)
            except TimeoutError:
                pass
    finally:
        _logger.info("end reader of %s", device.name)
        publish(None)


async def periodic_average(q_in: asyncio.Queue, sink: Sink, interval: float):
    """Average the measurements in q_in every interval and send them to sink.

    Registration messages (cmd 'id') are sent immediately.
    The pending measurements are averaged and sent when
    None is received or the task is cancelled.
    """
    loop = asyncio.get_running_loop()
    buffer = []

    async def flush():
        nonlocal buffer
        _logger.debug("process buffer, len=%d", len(buffer))
        if buffer:
            result = avg_device_buffer(buffer)
            buffer = []
            # Send result to output if value is valid
            if result["valid"]:
                await sink.send(result)
            else:
                _logger.warning("average of measurements is not valid, ignoring")

    deadline = loop.time() + interval
    try:
        while True:
            try:
                payload = await asyncio.wait_for(q_in.get(), timeout=max(deadline - loop.time(), 0))
            except TimeoutError:
                await flush()
                deadline += interval
                continue

            if payload is None:
                # None is a signal to exit
                break
            elif payload["cmd"] == "id":
                await sink.send(payload)
            elif payload["cmd"] == "r":
                buffer.append(payload)
            else:
                _logger.warning("unknown cmd, %s", payload)
    finally:
        # Do not lose pending measurements on exit
        while not q_in.empty():
            payload = q_in.get_nowait()
            if payload is not None and payload["cmd"] == "r":
                buffer.append(payload)
        await flush()


async def forward_measurements(q_in: asyncio.Queue, sink: Sink):
    """Send the measurements in q_in to sink without averaging.

    Measurements that are not valid are ignored. Ends when None is received.
    """
    while True:
        payload = await q_in.get()
        if payload is None:
            # None is a signal to exit
            break
        if payload["cmd"] == "r" and not payload.get("valid", True):
            _logger.debug("measurement is not valid, ignoring %s", payload)
            continue
        await sink.send(payload)


def avg_device_buffer(payloads):
    """Average n measurements"""
    npayloads = len(payloads)
    result = dict(payloads[0])
    result["valid"] = True

    # we have to average tstamp, freq_sensor and magnitude
    vals = [p for p in payloads if p["freq_sensor"] > 0]
    # TODO: analyze extreme values, etc.
    if len(vals) != len(payloads):
        msg = "some measurements have freq <= 0"
        warnings.warn(msg, RuntimeWarning)

    if vals:
        # Computing median
        result["freq_sensor"] = float(numpy.median([p["freq_sensor"] for p in vals]))
        # The magnitude is not recomputed from the frequency: the one
        # given by the device includes its corrections (dark current,
        # temperature). Under dark skies the difference is ~0.06 mag in SQM
        result["magnitude"] = float(numpy.median([p["magnitude"] for p in vals]))
    else:
        result["freq_sensor"] = 0
        result["magnitude"] = -99
        result["valid"] = False

    # These two are averages
    for key in ["temp_ambient", "temp_sky"]:
        temps = [p[key] for p in payloads if p.get(key) is not None]
        if temps:
            result[key] = float(numpy.mean(temps))

    # Time is average of times
    ts0 = result["tstamp"]
    ts = [(p["tstamp"] - ts0) for p in payloads]
    result["tstamp"] = ts0 + sum(ts, datetime.timedelta(0)) / npayloads
    return result
