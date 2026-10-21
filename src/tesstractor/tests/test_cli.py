import asyncio
import configparser
import os
import pkgutil
import signal

import pytest

from ..cli import main, build_location_from_ini, run_service, build_dev_from_ini, readerconf_from_ini


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


async def run_with_file(tmp_path, interval):
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
