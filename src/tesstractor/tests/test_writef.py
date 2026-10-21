import configparser
import datetime
import os

import astropy.table
import pytest
import pytz

import tesstractor.reader  # noqa: F401, registers the IDA format
from ..cli import LocationConf, static_conf_from_ini
from ..sqm import SQMTest
from ..tess import TessR
from ..writef import init_file
from .fakes import StreamSerial
from ..writef import FileSink, TimedDailyRotator, startup
from ..workers import avg_device_buffer

TZ = pytz.timezone("Europe/Madrid")


def location():
    return LocationConf(latitude="40.4189", longitude="-3.6919", elevation="650", timezone="Europe/Madrid")


def test_location_converters():
    loc = location()
    assert loc.latitude == 40.4189


async def test_file_sink_roundtrip(tmp_path):
    dev = SQMTest()
    dev.start_connection()
    conf = dev.static_conf()
    conf.altitude = 80.0
    conf.azimuth = 0.0
    sink = FileSink(str(tmp_path / "sub"), conf, location(), TZ)
    # The directory is created
    sink.open()
    # Registration is not written
    await sink.send(dict(cmd="id", name="sqmtest"))
    data = dict(dev.read_data(), localtz=TZ)
    for _ in range(3):
        await sink.send(avg_device_buffer([data]))

    (fname,) = os.listdir(tmp_path / "sub")
    with open(tmp_path / "sub" / fname) as fd:
        content = fd.read()
    assert "# Number of fields per line: 7" in content
    # Zenith and azimuth, in that order
    assert "# Measurement direction per channel: 10.0, 0.0" in content
    assert "# Position: 40.4189, -3.6919, 650\n" in content
    # SQM has no sky temperature, the field is empty
    data_line = content.splitlines()[-1]
    assert data_line.split(";")[2:4] == ["29.90", ""]

    tab = astropy.table.Table.read(str(tmp_path / "sub" / fname), format="ascii.IDA")
    assert len(tab) == 3
    assert tab.meta["lat"].value == pytest.approx(40.4189)
    assert tab.meta["lon"].value == pytest.approx(-3.6919)
    assert tab["temp"][0] == pytest.approx(29.9)
    # Empty fields are masked
    assert tab["sky_temp"].mask.all()
    assert tab["mag"].dtype.kind == "f"
    # No time zone suffix in the times
    assert len(tab["time_utc"][0]) == 23


def test_startup_reuses_file(tmp_path):
    rot = TimedDailyRotator(when=datetime.time(12))
    inter = rot.in_interval(datetime.datetime(2026, 1, 2, 3, 0, 0))
    # File created at the start of the interval
    (tmp_path / "20260101_120000_sqm1.dat").touch()
    (tmp_path / "20251231_130000_sqm1.dat").touch()
    create, fname = startup(inter, "sqm1", str(tmp_path))
    assert not create
    assert fname == "20260101_120000_sqm1.dat"


def test_startup_new_file(tmp_path):
    rot = TimedDailyRotator(when=datetime.time(12))
    inter = rot.in_interval(datetime.datetime(2026, 1, 2, 13, 0, 0))
    (tmp_path / "20260101_120000_sqm1.dat").touch()
    create, fname = startup(inter, "sqm1", str(tmp_path))
    assert create


def header(tmp_path, conf):
    fname = tmp_path / "header.dat"
    init_file(str(fname), conf, location())
    with open(fname) as fd:
        lines = fd.read().splitlines()
    assert len(lines) == 35
    return lines


def test_header_values_not_provided_are_empty(tmp_path):
    dev = TessR(StreamSerial([]), "tess1")
    lines = header(tmp_path, dev.static_conf())
    for key in ["Filters per channel", "Measurement direction per channel", "Field of view"]:
        assert f"# {key}:" in lines
    for key in ["TESS MAC address", "TESS firmware version", "TESS cover offset value"]:
        assert f"# {key}:" in lines


def test_header_values_from_configuration(tmp_path):
    cparser = configparser.ConfigParser()
    cparser.read_dict(
        {"photometer": dict(filter="HOYA CM-500", azimuth="0", altitude="90", fov="20", cover_offset="-0.11")}
    )
    dev = SQMTest()
    dev.start_connection()
    lines = header(tmp_path, static_conf_from_ini(dev, cparser["photometer"]))
    assert "# Filters per channel: HOYA CM-500" in lines
    assert "# Measurement direction per channel: 0.0, 0.0" in lines
    assert "# Field of view: 20.0" in lines
    assert "# SQM cover offset value: -0.11" in lines
    assert "# SQM firmware version: 23" in lines
