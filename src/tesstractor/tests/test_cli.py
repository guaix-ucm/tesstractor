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


async def test_run_service(tmp_path):
    cparser = configparser.ConfigParser()
    cparser.read_dict(
        {
            "photometer": {"model": "SQM-TEST", "tsample": "0.01"},
            "location": {"latitude": "40.4", "longitude": "-3.7", "timezone": "Europe/Madrid"},
            "file": {"dirname": str(tmp_path), "interval": "3600"},
        }
    )
    dev = build_dev_from_ini(cparser["photometer"])
    photometers = [(dev, readerconf_from_ini(cparser["photometer"]), cparser["photometer"])]
    loc = build_location_from_ini(cparser)

    loop = asyncio.get_running_loop()
    loop.call_later(0.2, os.kill, os.getpid(), signal.SIGTERM)
    await run_service(cparser, photometers, loc)
    for signum in [signal.SIGTERM, signal.SIGINT]:
        loop.remove_signal_handler(signum)

    (fname,) = os.listdir(tmp_path)
    with open(tmp_path / fname) as fd:
        lines = [line for line in fd if not line.startswith("#")]
    # The interval is long, the average is written on exit
    assert len(lines) == 1
