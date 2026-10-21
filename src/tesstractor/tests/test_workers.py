import asyncio
import datetime

import pytest
import pytz

from ..sqm import SQMTest
from ..workers import avg_device_buffer, forward_measurements, periodic_average, put_drop_oldest, read_photometer

T0 = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)


def payload(freq, dt=0, **kwargs):
    res = dict(
        cmd="r",
        name="sqm1",
        model="SQM",
        magnitude=20.0,
        freq_sensor=freq,
        zero_point=19.89,
        valid=True,
        tstamp=T0 + datetime.timedelta(seconds=dt),
    )
    res.update(kwargs)
    return res


def test_avg_dark_sky():
    # Under dark skies the frequency is below 1 Hz
    res = avg_device_buffer([payload(0.3), payload(0.32, 2), payload(0.31, 4)])
    assert res["valid"]
    assert res["freq_sensor"] == pytest.approx(0.31)
    assert res["tstamp"] == T0 + datetime.timedelta(seconds=2)


def test_avg_no_valid_freq():
    with pytest.warns(RuntimeWarning):
        res = avg_device_buffer([payload(0), payload(0)])
    assert not res["valid"]


def test_avg_missing_temperatures():
    res = avg_device_buffer([payload(1.0, temp_ambient=10.0), payload(1.0), payload(1.0, temp_ambient=12.0)])
    assert res["temp_ambient"] == 11.0
    assert "temp_sky" not in res


def test_put_drop_oldest():
    q = asyncio.Queue(maxsize=2)
    for i in range(3):
        put_drop_oldest(q, i)
    assert [q.get_nowait(), q.get_nowait()] == [1, 2]


class ListSink:
    def __init__(self):
        self.items = []

    async def send(self, payload):
        self.items.append(payload)


async def test_periodic_average_flushes_on_end():
    q = asyncio.Queue()
    sink = ListSink()
    q.put_nowait(dict(cmd="id", name="sqm1"))
    q.put_nowait(payload(1.0))
    q.put_nowait(payload(1.0))
    q.put_nowait(None)
    # The interval is long, the average is sent at the end
    await periodic_average(q, sink, 3600)
    assert [p["cmd"] for p in sink.items] == ["id", "r"]


async def test_periodic_average_interval():
    q = asyncio.Queue()
    sink = ListSink()
    task = asyncio.create_task(periodic_average(q, sink, 0.05))
    q.put_nowait(payload(1.0))
    await asyncio.sleep(0.1)
    assert len(sink.items) == 1
    q.put_nowait(payload(2.0))
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    # Pending measurement sent on cancellation
    assert len(sink.items) == 2


async def test_read_photometer():
    dev = SQMTest()
    dev.start_connection()
    q = asyncio.Queue()
    stop = asyncio.Event()
    readerconf = dict(nsamples=2, tsample=0.01, tz=pytz.timezone("Europe/Madrid"))
    task = asyncio.create_task(read_photometer(dev, [q], readerconf, stop))
    await asyncio.sleep(0.1)
    stop.set()
    await task
    items = []
    while not q.empty():
        items.append(q.get_nowait())
    assert items[0]["cmd"] == "id"
    assert items[1]["cmd"] == "r"
    assert items[1]["seq"] == 0
    assert items[-1] is None


async def test_forward_measurements():
    q = asyncio.Queue()
    sink = ListSink()
    q.put_nowait(dict(cmd="id", name="sqm1"))
    q.put_nowait(payload(1.0, magnitude=17.54))
    q.put_nowait(payload(0.0, valid=False))
    q.put_nowait(payload(2.0, magnitude=17.12))
    q.put_nowait(None)
    await forward_measurements(q, sink)
    # Invalid measurements are ignored, the rest are not modified
    assert [p["cmd"] for p in sink.items] == ["id", "r", "r"]
    assert [p.get("magnitude") for p in sink.items[1:]] == [17.54, 17.12]


async def test_read_photometer_without_averaging():
    dev = SQMTest()
    dev.start_connection()
    q = asyncio.Queue()
    stop = asyncio.Event()
    readerconf = dict(nsamples=1, tsample=0.01, tz=pytz.timezone("Europe/Madrid"))
    task = asyncio.create_task(read_photometer(dev, [q], readerconf, stop))
    await asyncio.sleep(0.1)
    stop.set()
    await task
    items = []
    while not q.empty():
        items.append(q.get_nowait())
    readings = [p for p in items if p is not None and p["cmd"] == "r"]
    assert [p["seq"] for p in readings] == list(range(len(readings)))
    # Magnitude as given by the device
    assert all(p["magnitude"] == 19.29 for p in readings)


def test_avg_keeps_device_magnitude():
    # Covered SQM-LU 2747: the device gives 22.49, the frequency
    # without its dark and temperature corrections gives 22.43
    freq = 460800 / 4770416
    res = avg_device_buffer([payload(freq, i, magnitude=mag) for i, mag in enumerate([22.49, 22.48, 22.50])])
    assert res["magnitude"] == 22.49
    assert res["freq_sensor"] == pytest.approx(freq)


def test_avg_ignores_magnitude_of_invalid():
    with pytest.warns(RuntimeWarning):
        res = avg_device_buffer(
            [payload(0, magnitude=99.0), payload(1.0, magnitude=20.0), payload(1.0, magnitude=20.2)]
        )
    assert res["magnitude"] == pytest.approx(20.1)
