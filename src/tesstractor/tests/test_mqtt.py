import asyncio
import configparser
import datetime
import json

import aiomqtt
import pytz

from ..mqtt import MqttSink, format_reading, format_register

T0 = datetime.datetime(2026, 1, 1, 10, 0, 0, 600000, tzinfo=datetime.UTC)


def mqtt_config():
    cparser = configparser.ConfigParser()
    cparser.read_dict(
        {
            "mqtt": dict(
                hostname="localhost",
                username="tess",
                password="x",
                register_topic="STARS4ALL/register",
                publish_topic="STARS4ALL/{name}/reading",
                reconnect_interval="0",
            )
        }
    )
    return cparser["mqtt"]


REGISTER = dict(cmd="id", name="sqm1", model="SQM-LU", mac="2747", calib=19.89, rev=1, tstamp=T0, localtz=pytz.utc)
READING = dict(cmd="r", name="sqm1", freq_sensor=8.614, magnitude=17.55, temp_ambient=21.2, tstamp=T0)


def test_format_register():
    res = json.loads(format_register(REGISTER, "STARS4ALL/{name}/reading"))
    assert res["tstamp"] == "2026-01-01T10:00:01"
    assert res["chan"] == "STARS4ALL/sqm1/reading"
    assert "localtz" not in res


def test_format_reading():
    topic, msg = format_reading(READING, 3, "STARS4ALL/{name}/reading")
    assert topic == "STARS4ALL/sqm1/reading"
    res = json.loads(msg)
    assert res == dict(
        seq=3, name="sqm1", freq=8.614, mag=17.55, tamb=21.2, tsky=0.0, rev=1, tstamp="2026-01-01T10:00:01"
    )


class FakeClient:
    def __init__(self, log, fail):
        self.log = log
        self.fail = fail

    async def __aenter__(self):
        if self.fail:
            raise aiomqtt.MqttError("connection refused")
        self.log.append(("connect",))
        return self

    async def __aexit__(self, *args):
        self.log.append(("disconnect",))

    async def publish(self, topic, payload, qos=0):
        self.log.append((topic, payload))


async def test_sink_reconnects_and_registers():
    log = []
    fails = [True, False]
    sink = MqttSink(mqtt_config())
    sink._client = lambda: FakeClient(log, fails.pop(0))

    task = asyncio.create_task(sink.run())
    await sink.send(REGISTER)
    await sink.send(READING)
    await sink.send(READING)
    await asyncio.sleep(0.01)
    await sink.close()
    await task

    topics = [entry[0] for entry in log]
    assert topics == [
        "connect",
        "STARS4ALL/register",
        "STARS4ALL/sqm1/reading",
        "STARS4ALL/sqm1/reading",
        "disconnect",
    ]
    assert json.loads(log[3][1])["seq"] == 2


async def test_sink_gives_up_when_closing():
    sink = MqttSink(mqtt_config())
    sink._client = lambda: FakeClient([], True)
    await sink.send(READING)
    await sink.close()
    # Does not block if the server is not available
    await sink.run()
