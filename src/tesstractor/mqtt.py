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
import json
import logging
import ssl

import aiomqtt

from tesstractor.workers import QUEUE_MAXSIZE, put_drop_oldest

_HALF_S = datetime.timedelta(seconds=0.5)

_MSG = (
    '"seq": {seq}, "name": "{name}", "freq": {freq:.3f}, "mag": {mag:.2f},'
    ' "tamb": {tamb:.1f}, "tsky": {tsky:.1f}, "rev": {rev}, "tstamp": "{tstamp}"'
)

# Signal the end of the messages
_END = object()

_logger = logging.getLogger(__name__)


def round_tstamp(tstamp):
    """Format the time stamp rounded to the nearest second"""
    return (tstamp + _HALF_S).strftime("%Y-%m-%dT%H:%M:%S")


def format_register(msg, publish_topic):
    """Format the registration message"""
    payload = dict(msg)
    del payload["cmd"]
    del payload["localtz"]
    payload.pop("tstamp_local", None)
    payload["tstamp"] = round_tstamp(msg["tstamp"])
    payload["chan"] = publish_topic.format(name=msg["name"])
    return json.dumps(payload)


def format_reading(msg, seq, publish_topic):
    """Format a measurement, return topic and message"""
    payload = dict(
        seq=seq,
        name=msg["name"],
        freq=msg["freq_sensor"],
        mag=msg["magnitude"],
        tamb=msg.get("temp_ambient", 0.0),
        tsky=msg.get("temp_sky", 0.0),
        rev=msg.get("protocol_revision", 1),
        tstamp=round_tstamp(msg["tstamp"]),
    )
    # With json.dumps I can't control numeric precision
    spayload = "{{{}}}".format(_MSG.format(**payload))
    topic = publish_topic.format(**payload)
    return topic, spayload


class MqttSink:
    """Send measurements to a MQTT server.

    Messages are queued and sent by `run`, that reconnects
    to the server when the connection is lost.
    """

    def __init__(self, config):
        self.hostname = config["hostname"]
        self.port = config.getint("port", 1883)
        self.username = config.get("username")
        self.password = config.get("password")
        self.tls = config.getboolean("tls", False)
        self.register_topic = config["register_topic"]
        self.publish_topic = config["publish_topic"]
        self.reconnect_interval = config.getfloat("reconnect_interval", 30.0)

        self.queue = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        # Registration messages, sent again on reconnection
        self.registers = {}
        self.seq = {}
        self.closing = False

    async def send(self, payload):
        put_drop_oldest(self.queue, payload)

    async def close(self):
        """Send the pending messages and end `run`"""
        self.closing = True
        put_drop_oldest(self.queue, _END)

    def _client(self):
        tls_context = ssl.create_default_context() if self.tls else None
        return aiomqtt.Client(
            self.hostname,
            self.port,
            username=self.username,
            password=self.password,
            tls_context=tls_context,
        )

    async def run(self):
        pending = None
        while True:
            try:
                _logger.info("open MQTT connection with %s:%d", self.hostname, self.port)
                async with self._client() as client:
                    for spayload in self.registers.values():
                        _logger.debug("sending register msg %s", spayload)
                        await client.publish(self.register_topic, spayload)
                    while True:
                        if pending is None:
                            pending = await self.queue.get()
                        if pending is _END:
                            _logger.info("end MQTT consumer")
                            return
                        await self._publish(client, pending)
                        pending = None
            except aiomqtt.MqttError as ex:
                _logger.warning("MQTT connection with %s failed: %s", self.hostname, ex)
                if self.closing:
                    _logger.warning("discarding %d MQTT messages", self.queue.qsize())
                    return
                await asyncio.sleep(self.reconnect_interval)

    async def _publish(self, client, msg):
        """Format payload and send it to server"""
        name = msg["name"]
        if msg["cmd"] == "id":
            # reset sequence number
            self.seq[name] = 1
            spayload = format_register(msg, self.publish_topic)
            self.registers[name] = spayload
            _logger.debug("sending register msg %s", spayload)
            await client.publish(self.register_topic, spayload)
        elif msg["cmd"] == "r":
            seq = self.seq.get(name, 1)
            topic, spayload = format_reading(msg, seq, self.publish_topic)
            _logger.debug("sending data %s", spayload)
            await client.publish(topic, spayload, qos=0)
            self.seq[name] = seq + 1
        else:
            _logger.warning("MQTT, msg cmd is unknown, %s", msg)
