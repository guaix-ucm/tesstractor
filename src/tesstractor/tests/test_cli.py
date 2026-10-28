import asyncio
import configparser
import os
import pkgutil
import signal

import pytest

from ..cli import main, build_location_from_ini, run_service, build_dev_from_ini, readerconf_from_ini, error_summary
from ..tess import TessV2
from .fakes import StreamSerial


def test_config(capsys):
    dtm = pkgutil.get_data("tesstractor", "base.ini")
    data = dtm.decode("utf-8")
    main(["-g"])
    out, err = capsys.readouterr()
    # last character in out is \n
    assert data == out[:-1]


def test_build_location():
    cparser = configparser.ConfigParser(defaults={"dirname": "/var/lib/tesstractor"})
    cparser.read_dict({"location": {"latitude": "40.4", "longitude": "-3.7", "timezone": "Europe/Madrid"}})
    loc = build_location_from_ini(cparser)
    assert loc.latitude == 40.4
    assert loc.longitude == -3.7
    assert not hasattr(loc, "dirname")


def test_unknown_model():
    cparser = configparser.ConfigParser()
    cparser.read_dict({"photometer": {"model": "XXX"}})
    with pytest.raises(ValueError):
        build_dev_from_ini(cparser["photometer"])


def test_build_tessv2(monkeypatch):
    monkeypatch.setattr("tesstractor.cli.serial.Serial", lambda *args, **kwargs: StreamSerial([]))
    cparser = configparser.ConfigParser()
    cparser.read_dict({"photometer": {"model": "TESSv2", "port": "/dev/null"}})
    dev = build_dev_from_ini(cparser["photometer"])
    assert isinstance(dev, TessV2)
    # Read from the photometer in start_connection
    assert dev.conf_name is None
    assert dev.conf_zero_point is None


async def run_with_file(tmp_path, interval, fail_after=None):
    """Run the service with SQM-TEST for a while, return the data lines of the file"""
    cparser = configparser.ConfigParser()
    cparser.read_dict(
        {
            "photometer": {"model": "SQM-TEST", "tsample": "0.01"},
            "location": {"latitude": "40.4", "longitude": "-3.7", "timezone": "Europe/Madrid"},
            "file": {"dirname": str(tmp_path), "interval": interval},
        }
    )
    dev = build_dev_from_ini(cparser["photometer"])
    if fail_after is not None:
        # The device is disconnected after fail_after readings
        good_read_data = dev.read_data
        readings = []

        def read_data(tries=1):
            if len(readings) >= fail_after:
                raise OSError("device disconnected")
            readings.append(1)
            return good_read_data(tries)

        dev.read_data = read_data
    photometers = [(dev, readerconf_from_ini(cparser["photometer"]), cparser["photometer"])]
    loc = build_location_from_ini(cparser)

    loop = asyncio.get_running_loop()
    handle = loop.call_later(0.2, os.kill, os.getpid(), signal.SIGTERM)
    try:
        await run_service(cparser, photometers, loc)
    finally:
        handle.cancel()
        for signum in [signal.SIGTERM, signal.SIGINT]:
            loop.remove_signal_handler(signum)

    (fname,) = os.listdir(tmp_path)
    with open(tmp_path / fname) as fd:
        return [line for line in fd if not line.startswith("#")]


async def test_run_service(tmp_path):
    lines = await run_with_file(tmp_path, "3600")
    # The interval is long, the average is written on exit
    assert len(lines) == 1


async def test_run_service_without_averaging(tmp_path):
    lines = await run_with_file(tmp_path, "0")
    # Every measurement is written
    assert len(lines) > 3
    # The magnitude is the one given by the device, not recomputed
    assert all(line.split(";")[5] == "19.29" for line in lines)


async def test_run_service_negative_interval(tmp_path):
    with pytest.raises(ValueError, match="interval"):
        await run_with_file(tmp_path, "-1")


def test_error_summary():
    error = OSError(5, "Input/output error")
    error.add_note("photometer sqm1")
    group = ExceptionGroup("tasks", [ExceptionGroup("producers", [error]), ValueError("bad interval")])
    assert error_summary(group) == ("photometer sqm1: OSError: [Errno 5] Input/output error; ValueError: bad interval")


@pytest.mark.parametrize("fail_after", [0, 3])
async def test_run_service_names_failed_photometer(tmp_path, fail_after):
    # Fails in start_connection (0) or while reading (3)
    with pytest.raises(Exception) as excinfo:
        await run_with_file(tmp_path, "0", fail_after=fail_after)
    assert error_summary(excinfo.value) == "photometer sqmtest: OSError: device disconnected"


def test_main_missing_port(tmp_path, caplog):
    config = tmp_path / "config.ini"
    config.write_text("[photometer]\nmodel: SQM-LU\nport: /dev/does-not-exist\n")
    with pytest.raises(SystemExit) as excinfo:
        main(["-c", str(config)])
    assert excinfo.value.code == 1
    assert "ending with error: section photometer: SerialException: [Errno 2] could not open port" in caplog.text
