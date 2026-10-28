#
# Copyright 2018-2024 Universidad Complutense de Madrid
#
# This file is part of tesstractor
#
# SPDX-License-Identifier: GPL-3.0-or-later
# License-Filename: LICENSE.txt
#

import asyncio
import signal
import logging
import argparse
import configparser
import pkgutil
import sys

import serial
import attr
import pytz

from tesstractor.sqm import SQMTest, SQMLU
from tesstractor.tess import TessR, TessV2
from tesstractor.device import Device
from tesstractor.mqtt import MqttSink
from tesstractor.writef import FileSink
from tesstractor.workers import QUEUE_MAXSIZE, read_photometer, periodic_average, forward_measurements

ini_defaults = {
    "provider": {"contact_name": "unknown", "organization": "unknown"},
    "location": {
        "locality": "unknown",
        "province": "unknown",
        "country": "unknown",
        "site": "unknown",
        #
        "latitude": 0.0,
        "longitude": 0.0,
        "elevation": 0.0,
        #
        "timezone": "UTC",
        "timesync": "unknown",
    },
}

# Fields of the instrument configuration that can be set in the ini file
_instrument_keys = {
    "filter": str,
    "azimuth": float,
    "altitude": float,
    "fov": float,
    "cover_offset": float,
}


@attr.s
class LocationConf:
    contact_name = attr.ib(default="")
    organization = attr.ib(default="")
    locality = attr.ib(default="")
    province = attr.ib(default="")
    country = attr.ib(default="")
    site = attr.ib(default="")

    latitude = attr.ib(converter=float, default=0.0)
    longitude = attr.ib(converter=float, default=0.0)
    elevation = attr.ib(converter=float, default=0.0)

    timezone = attr.ib(default="UTC")
    timesync = attr.ib(default="")


def build_location_from_ini(conf) -> LocationConf:
    """Create a locationConf from the configuration"""
    location_sec = conf["location"]
    fields = attr.fields_dict(LocationConf)
    kwargs = {key: location_sec[key] for key in location_sec if key in fields}
    return LocationConf(**kwargs)


def build_dev_from_ini(section) -> Device:
    """Create a Device from the configuration"""
    logger = logging.getLogger(__name__)

    model = section.get("model", "SQM-TEST")
    logger.debug("model is %s", model)
    name = section.get("name")
    port = section.get("port", "/dev/ttyUSB0")
    if model == "SQM-TEST":
        return SQMTest()
    elif model == "SQM-LU":
        baudrate = section.getint("baudrate", 115200)
        timeout = section.getfloat("timeout", 2.0)
        conn = serial.Serial(port, baudrate, timeout=timeout)
        photo_dev = SQMLU(conn, name)
    elif model in ["TESS-R", "TESS", "TESS-U"]:
        baudrate = section.getint("baudrate", 9600)
        timeout = section.getfloat("timeout", 1.0)
        conn = serial.Serial(port, baudrate, timeout=timeout)
        if name is None:
            logger.warning("name is none, this should be automatic")
            name = "TESS-test"
        photo_dev = TessR(conn, name)
        photo_dev.calibration = section.getfloat("zero_point", 20.0)
    elif model == "TESSv2":
        baudrate = section.getint("baudrate", 9600)
        timeout = section.getfloat("timeout", 1.0)
        conn = serial.Serial(port, baudrate, timeout=timeout)
        # The photometer reports its name and zero point
        photo_dev = TessV2(conn, name, section.getfloat("zero_point"))
    else:
        raise ValueError("unknown model {}".format(model))

    mac = section.get("mac")
    if mac:
        photo_dev.mac = mac
    return photo_dev


def static_conf_from_ini(device: Device, section):
    """Configuration of the instrument, with values from the configuration"""
    conf = device.static_conf()
    for key, conv in _instrument_keys.items():
        if key in section:
            setattr(conf, key, conv(section[key]))
    return conf


def readerconf_from_ini(section):
    readerconf = dict()
    readerconf["nsamples"] = section.getint("nsamples", 0)
    readerconf["tsample"] = section.getfloat("tsample", 1.0)
    return readerconf


def output_interval(section, default):
    """Interval to average the measurements, 0 to send them without averaging"""
    interval = section.getfloat("interval", default)
    if interval < 0:
        raise ValueError(f"interval in section {section.name} must be >= 0, is {interval}")
    return interval


def enabled_sections(cparser, prefix):
    """Sections starting with prefix, that are enabled"""
    logger = logging.getLogger(__name__)
    result = []
    for sec_name in cparser.sections():
        if sec_name.startswith(prefix):
            if cparser[sec_name].getboolean("enabled", True):
                result.append(cparser[sec_name])
            else:
                logger.info("section %s disabled", sec_name)
    return result


async def start_connection(device: Device):
    """Read the metadata of the device"""
    try:
        # Serial I/O is blocking
        await asyncio.to_thread(device.start_connection)
    except Exception as ex:
        ex.add_note(f"photometer {device.name}")
        raise


def error_summary(ex: BaseException) -> str:
    """The causes of an exception in one line, also for exception groups"""
    if isinstance(ex, BaseExceptionGroup):
        return "; ".join(error_summary(sub) for sub in ex.exceptions)
    notes = "".join(f"{note}: " for note in getattr(ex, "__notes__", []))
    return f"{notes}{type(ex).__name__}: {ex}"


async def run_service(cparser, photometers, loc_conf):
    """Read the photometers and send the measurements to files and MQTT servers.

    Ends when SIGTERM or SIGINT are received. If any task fails,
    the rest are cancelled and the exception is raised.
    """
    logger = logging.getLogger(__name__)
    loc_tz = pytz.timezone(loc_conf.timezone)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in [signal.SIGTERM, signal.SIGINT]:
        loop.add_signal_handler(signum, stop.set)

    mqtt_sinks = []
    for sec in enabled_sections(cparser, "mqtt"):
        logger.info("creating MQTT connection with %s", sec["hostname"])
        mqtt_sinks.append((MqttSink(sec), output_interval(sec, 60.0)))

    file_secs = [(sec, output_interval(sec, 300.0)) for sec in enabled_sections(cparser, "file")]

    # Read metadata and calibration
    await asyncio.gather(*(start_connection(dev) for dev, _, _ in photometers))

    async with asyncio.TaskGroup() as tg:
        for sink, _ in mqtt_sinks:
            tg.create_task(sink.run())

        async with asyncio.TaskGroup() as producers:
            for dev, readerconf, dev_sec in photometers:
                sinks = [(sink, interval) for sink, interval in mqtt_sinks]
                for sec, interval in file_secs:
                    sink = FileSink(sec.get("dirname"), static_conf_from_ini(dev, dev_sec), loc_conf, loc_tz)
                    sink.open()
                    sinks.append((sink, interval))

                queues = []
                for sink, interval in sinks:
                    q = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
                    queues.append(q)
                    if interval > 0:
                        producers.create_task(periodic_average(q, sink, interval))
                    else:
                        producers.create_task(forward_measurements(q, sink))

                readerconf["tz"] = loc_tz
                producers.create_task(read_photometer(dev, queues, readerconf, stop))

        # Readers have ended, send pending messages
        for sink, _ in mqtt_sinks:
            await sink.close()


def main(args=None):
    # Parse CLI
    parser = argparse.ArgumentParser()
    parser.add_argument("--dirname")
    parser.add_argument("-c", "--config")
    parser.add_argument("-g", "--generate-config", action="store_true")
    parser.add_argument(
        "--log",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "NOTSET"],
    )

    pargs = parser.parse_args(args=args)

    loglevel = getattr(logging, pargs.log.upper())

    logging.basicConfig(level=loglevel)
    logger = logging.getLogger(__name__)
    logger.info("tesstractor, starting")

    if pargs.generate_config:
        # write the default config file
        data = pkgutil.get_data("tesstractor", "base.ini")
        print(data.decode("utf-8"))
        return 0

    cparser = configparser.ConfigParser(defaults={"dirname": "/var/lib/tesstractor"})

    cparser.read_dict(ini_defaults)
    if pargs.config:
        cparser.read(pargs.config)

    ini_overrides = {}
    if pargs.dirname is not None:
        ini_overrides["file"] = {}
        ini_overrides["file"]["dirname"] = pargs.dirname

    cparser.read_dict(ini_overrides)

    try:
        loc_conf = build_location_from_ini(cparser)

        photometers = []
        for section in enabled_sections(cparser, "photometer"):
            try:
                # Opens the serial port
                newdev = build_dev_from_ini(section)
            except Exception as ex:
                ex.add_note(f"section {section.name}")
                raise
            newread = readerconf_from_ini(section)
            photometers.append((newdev, newread, section))

        if not photometers:
            logger.warning("No devices enabled. Exit")
            sys.exit(1)

        asyncio.run(run_service(cparser, photometers, loc_conf))
    except Exception as ex:
        logger.exception("tesstractor, ending with error: %s", error_summary(ex))
        sys.exit(1)

    logger.info("tesstractor, ending")
    sys.exit(0)


if __name__ == "__main__":
    main()
