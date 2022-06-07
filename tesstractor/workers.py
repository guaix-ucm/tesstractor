#
# Copyright 2018-2022 Universidad Complutense de Madrid
#
# This file is part of tesstractor
#
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSE.txt
#

import datetime
import threading
import logging
import typing
import math
import queue

import tzlocal
import numpy

from tesstractor.sqm import Device


_logger = logging.getLogger(__name__)


def read_photometer_timed(
        device: Device,
        output_q: queue.Queue,
        readerconf,
        exit_event: threading.Event,
        error_event: threading.Event
):
    thisth = threading.current_thread()
    _logger.info('starting {} thread'.format(thisth.name))
    seq = 0

    internal_buffer = []

    nsamples = readerconf.get('nsamples', 5)
    exit_check_timeout = 1
    # print('(1)timed_reader, reading every ', timeout, 's')
    # initialice connection. read metadata and calibration

    try:
        # already done by start_connection
        # device.read_metadata()
        # Read calibration
        # device.read_calibration()

        mac = str(device.serial_number)
        now = datetime.datetime.utcnow()
        local_tz = readerconf.get('tz', tzlocal.get_localzone())

        payload_init = dict(
            name=device.name,
            model=device.model,
            mac=mac,
            calib=device.calibration,
            rev=1,
            cmd='id',
            tstamp=now,
            localtz=local_tz
        )

        output_q.put(payload_init)
        # exit after this
        # q.put(None)
        # exit_event.set()

        # Check if exit_event is set. If it is not set,
        # wait a little (exit_check_timeout) and continue
        do_exit = exit_event.wait(timeout=exit_check_timeout)

        tries = 3
        while not do_exit:
            # now = datetime.datetime.utcnow()
            # local_tz = tzlocal.get_localzone()
            # now_utc = pytz.utc.localize(now)
            # now_local = now_utc.astimezone(local_tz)

            msg = device.read_data(tries=tries)
            if msg is None:
                continue

            # print('(R)timed_reader loop', msg)
            # FIXME: this could be inside read_data
            payload = dict(msg)
            payload['localtz'] = local_tz
            _logger.debug(f'payload is {payload}')
            internal_buffer.append(payload)
            _logger.debug(f'nsamples is {len(internal_buffer)}')

            # When we have enough measurements, we collapse

            if len(internal_buffer) >= nsamples:
                _logger.debug('averaging {} samples'.format(len(internal_buffer)))
                # print('(R) enough samples', len(buffer))
                # do average
                res = avg_device_buffer(internal_buffer)
                res['seq'] = seq
                # reset buffer
                internal_buffer = []
                _logger.debug('buffer avg is {}'.format(res))
                _logger.debug('reset buffer {}'.format(internal_buffer))
                # Send averaged measurement for further work
                output_q.put(res)
                seq += 1
            # Check if exit_event is set. If it is not set,
            # wait a little (exit_check_timeout) and continue
            do_exit = exit_event.wait(timeout=exit_check_timeout)
    except Exception as ex:
        _logger.debug('exception happened %s', ex)
        error_event.set()
    finally:
        _logger.debug('end read thread')
        _logger.debug('signalling producers to end')
        exit_event.set()
        _logger.debug('signalling consumers to end')
        output_q.put(None)


def avg_device_buffer(payloads):
    """Average n measurements"""
    npayloads = len(payloads)
    result = dict(payloads[0])

    # we have to average
    # tstamp and freq_sensor
    # magnitude corresponds to the mag of the average freq
    zero_point = result['zero_point']

    vals = [p['freq_sensor'] for p in payloads]
    # TODO: analyze if there are values <= 0, extreme values, etc.
    vals_0 = list(filter(lambda x: x > 0, vals))
    if len(vals_0) != len(vals):
        print("WARNING, some measurements have freq <= 0")

    if vals_0:
        # Computing median
        result['freq_sensor'] = numpy.median(vals_0)
        result['magnitude'] = zero_point - 2.5 * math.log10(result['freq_sensor'])
    else:
        result['freq_sensor'] = 0
        result['magnitude'] = -99

    # These two are averages
    for key in ['temp_ambient', 'temp_sky']:
        if key in result:
            result[key] = numpy.mean([p[key] for p in payloads])

    # Time is average of times
    ts0 = result['tstamp']
    ts = [(p['tstamp'] - ts0) for p in payloads]
    result['tstamp'] = ts0 + sum(ts, datetime.timedelta(0)) / npayloads
    return result


def splitter(inputq: queue.Queue, qs: typing.Sequence[queue.Queue]):
    """Reads the input queue and sends the values to all the queues"""
    thisth = threading.current_thread()
    _logger.debug('starting {} thread'.format(thisth.name))
    while True:
        payload = inputq.get()
        inputq.task_done()
        for wq in qs:
            # Sending to all tasks...
            wq.put(payload)
        if payload is None:
            _logger.debug('end {} thread'.format(thisth.name))
            break


def simple_buffer(q_in, q_out, q_buffer, other):
    """Separates payload per command

    If cmd is 'r', goes to q_buffer
    If cmd is 'id', it goes q_to out
    """
    thisth = threading.current_thread()
    _logger.debug(f'starting filter buffer thread, {thisth.name}')
    while True:
        payload = q_in.get()
        if payload:
            if payload['cmd'] == 'id':
                q_out.put(payload)
            elif payload['cmd'] == 'r':
                q_buffer.put(payload)
            else:
                _logger.warning(f'unknown cmd, {payload}')
            q_in.task_done()
        else:
            # If payload is None is a signal to exit
            # put None in all queues and exit
            q_out.put(None)
            q_buffer.put(None)
            _logger.debug(f'end {thisth.name} thread')
            break


def periodic_avg_task(q_in1: queue.Queue, q_out: queue.Queue, other):
    """Average the buffer periodically"""

    thisth = threading.current_thread()
    # thisth is a Timer, it has interval
    interval = thisth.interval

    _logger.debug(f'wakeup timer thread, {thisth.name}')
    # other.set()

    # copy queue in buffer
    buffer = []
    _logger.debug('fill buffer, empty input queue')
    try:
        while True:
            p = q_in1.get_nowait()
            if p is None:
                # None is a signal to exit
                return
            buffer.append(p)
            q_in1.task_done()
    except queue.Empty:
        pass

    _logger.debug(f'process buffer, len={len(buffer)}')
    if buffer:
        # Queue processed value
        result = avg_device_buffer(buffer)
        # Send result to output queue
        q_out.put(result)
    else:
        pass

    # After doing the work, start a new timed thread
    _logger.debug(f'launch new timer thread, {thisth.name}')
    t = threading.Timer(interval, periodic_avg_task, args=(q_in1, q_out, other))
    t.name = thisth.name
    t.start()
