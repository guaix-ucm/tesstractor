#
# Copyright 2018-2022 Universidad Complutense de Madrid
#
# This file is part of tesstractor
#
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSE.txt
#

import threading
import queue
import signal
import logging
import argparse
import configparser
import sys
from typing import List

import serial
import attr
import pytz

from tesstractor.sqm import SQMTest, SQMLU
# from tesstractor.tess import Tess
from tesstractor.device import Device
import tesstractor.mqtt as mqtt
import tesstractor.writef
import tesstractor.tess
from tesstractor.workers import splitter, simple_buffer, periodic_avg_task, read_photometer_timed


def signal_handler_function(signum, frame, exit_event):
    """Communicate a exit event.

    All threads must finish
    """
    exit_event.set()


class Conf:
    pass


class OtherConf:
    pass


ini_defaults = {
    'provider': {
        'contact_name': 'unknown',
        'organization': 'unknown'
    },
    'location': {
        'locality': 'unknown',
        'province': 'unknown',
        'country': 'unknown',
        'site': 'unknown',
        #
        'latitude': 0.0,
        'longitude': 0.0,
        'elevation': 0.0,
        #
        'timezone': 'UTC',
        'timesync': 'unknown'
    }
}


@attr.s
class LocationConf:
    contact_name = attr.ib(default='')
    organization = attr.ib(default='')
    locality = attr.ib(default='')
    province = attr.ib(default='')
    country = attr.ib(default='')
    site = attr.ib(default='')

    latitude = attr.ib(converter=float, default=0.0)
    longitude = attr.ib(converter=float, default=0.0)
    elevation = attr.ib(converter=float, default=0.0)

    timezone = attr.ib(default='UTC')
    timesync = attr.ib(default='')


def build_location_from_ini(conf) -> LocationConf:
    """Create a locationConf from the configuration"""
    location_sec = conf['location']

    loc = LocationConf()
    for key in location_sec:
        setattr(loc, key, location_sec[key])

    return loc


def build_dev_from_ini(section) -> Device:
    """Create a Device from the configuration"""
    logger = logging.getLogger(__name__)

    model = section.get('model', 'SQM-TEST')
    logger.debug('model is %s', model)
    if model == 'SQM-TEST':
        return SQMTest()
    elif model == 'SQM-LU':
        name = section.get('name')
        port = section.get('port', '/dev/ttyUSB0')
        baudrate = section.getint('baudrate', 115200)
        timeout = section.getfloat('timeout', 2.0)
        conn = serial.Serial(port, baudrate, timeout=timeout)
        photo_dev = SQMLU(conn, name)
        mac = section.get('mac')
        if mac:
            photo_dev.mac = mac
        return photo_dev
    elif model in ['TESS-R', 'TESS', 'TESS-U']:
        name = section.get('name')
        port = section.get('port', '/dev/ttyUSB0')
        baudrate = section.getint('baudrate', 9600)
        timeout = section.getfloat('timeout', 1.0)
        conn = serial.Serial(port, baudrate, timeout=timeout)
        if name is None:
            logger.warning('name is none, this should be automatic')
            name = 'TESS-test'

        photo_dev = tesstractor.tess.TessR(conn, name)
        zero_point = section.getfloat('zero_point', 20.0)
        photo_dev.calibration = zero_point
        mac = section.get('mac')
        if mac:
            photo_dev.mac = mac

    elif model in ['TESSv2']:
        name = section.get('name')
        port = section.get('port', '/dev/ttyUSB0')
        baudrate = section.getint('baudrate', 9600)
        timeout = section.getfloat('timeout', 1.0)
        conn = serial.Serial(port, baudrate, timeout=timeout)
        if name is None:
            logger.warning('name is none, this should be automatic')
            name = 'TESS-test'

        photo_dev = tesstractor.tess.TessV2(conn, name)
        zero_point = section.getfloat('zero_point', 20.0)
        photo_dev.calibration = zero_point
        mac = section.get('mac')
        if mac:
            photo_dev.mac = mac

        return photo_dev
    else:
        raise ValueError('unkown model {}'.format(model))


def readerconf_from_ini(section):
    readerconf = dict()
    readerconf['nsamples'] = section.getint('nsamples', 0)
    readerconf['tsample'] = section.getfloat('tsample', 1.0)
    return readerconf


def create_mqtt_workers(
        q_worker: queue.Queue,
        mqtt_config) -> List[threading.Thread]:
    """Create MQTT workers"""
    otherx = OtherConf()
    # otherx.send_event = send_event

    q_mqtt_in = queue.Queue()  # Queue for MQTT
    q_buffer = queue.Queue()  # Queue for MQTT buffer

    filter_thread = threading.Thread(target=simple_buffer, name='simple_filter_mqtt',
                                     args=(q_worker, q_mqtt_in, q_buffer, otherx))

    interval = mqtt_config.getfloat('interval', 60.0)
    other_mqtt = mqtt.MqttConsumer(mqtt_config)
    consumer_mqtt = threading.Thread(
        target=mqtt.consumer_mqtt, name='mqtt_consumer',
        args=(q_mqtt_in, other_mqtt))

    send_event = None
    timed_buffer = threading.Timer(interval, periodic_avg_task, args=(q_buffer, q_mqtt_in, send_event))
    timed_buffer.name = 'timed_buffer_mqtt'

    filter_thread.start()
    timed_buffer.start()
    consumer_mqtt.start()

    return [filter_thread, consumer_mqtt]


def create_file_writer_workers(
        q_worker: queue.Queue,
        file_config: OtherConf) -> List[threading.Thread]:

    otherx = OtherConf()
    q_file_in = queue.Queue()  # Queue for file writer
    q_buffer = queue.Queue()   # Queue for file writer buffer
    send_event = None

    # This thread splits messages
    # cmd="ID" are sent directly to writer (q_file_in)
    # cmd="R" are sent to a buffer (q_buffer)
    filter_thread = threading.Thread(
        target=simple_buffer,
        name='simple_filter_file',
        args=(q_worker, q_file_in, q_buffer, otherx)
    )

    # This Timer thread wakes up periodically and averages values in (q_buffer)
    # After that, the average is sent to writer queue (q_file_in)
    interval = file_config.interval
    timed_buffer = threading.Timer(
        interval,
        periodic_avg_task,
        args=(q_buffer, q_file_in, send_event)
    )
    timed_buffer.name = 'timed_buffer_file'

    # This thread writes the values in writer queue (q_file_in)
    consumer_file = threading.Thread(
        target=tesstractor.writef.consumer_write_file,
        name='consumer_write_file',
        args=(q_file_in, file_config)
    )

    consumer_file.start()
    filter_thread.start()
    timed_buffer.start()

    return [filter_thread, consumer_file]


def main(args=None):
    # Register events and signal
    exit_event = threading.Event()
    error_event = threading.Event()
    send_event = threading.Event()

    exit_code = 0

    send_event.clear()

    def signal_handler(signum, frame):
        return signal_handler_function(signum, frame, exit_event)

    # On SIGTERM, set exit_event
    signal.signal(signal.SIGTERM, signal_handler)
    # On SIGINT, set exit_event
    signal.signal(signal.SIGINT, signal_handler)

    # Parse CLI
    parser = argparse.ArgumentParser()
    parser.add_argument('--dirname')
    parser.add_argument('-c', '--config')
    parser.add_argument('-g', '--generate-config', action='store_true')
    parser.add_argument("--log", default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRTICAL', 'NOTSET']
                        )

    pargs = parser.parse_args(args=args)

    loglevel = getattr(logging, pargs.log.upper())

    logging.basicConfig(level=loglevel)
    logger = logging.getLogger(__name__)
    logger.info('tesstractor, starting')

    if pargs.generate_config:
        # write the default config file
        import pkgutil
        data = pkgutil.get_data('tesstractor', 'base.ini')
        print(data.decode('utf-8'))
        return 0

    cparser = configparser.ConfigParser(defaults={'dirname': '/var/lib/tesstractor'})

    cparser.read_dict(ini_defaults)
    if pargs.config:
        cparser.read(pargs.config)

    ini_overrides = {
    }
    if pargs.dirname is not None:
        ini_overrides['file'] = {}
        ini_overrides['file']['dirname'] = pargs.dirname

    cparser.read_dict(ini_overrides)

    loc_conf = build_location_from_ini(cparser)
    loc_tz = pytz.timezone(loc_conf.timezone)
    photo_sections = [sec for sec in cparser.sections() if sec.startswith('photometer')]

    photolist = []
    readerlist = []
    for secname in photo_sections:
        section = cparser[secname]
        if section.getboolean('enabled', True):
            newdev = build_dev_from_ini(section)
            newread = readerconf_from_ini(section)
            newread['tz'] = loc_tz
            photolist.append(newdev)
            readerlist.append(newread)

    nsqm = len(photolist)

    if nsqm == 0:
        logger.warning('No devices enabled. Exit')
        sys.exit(1)

    # photoconf = []
    # for photodev in photolist:
    #    photodev.start_connection()
    #    photoconf.append(photodev.static_conf())

    # Using first device
    photo_dev = photolist[0]
    readerconf = readerlist[0]
    photo_dev.start_connection()

    # Working queues
    working_qs = []
    # joinable threads
    joinable_threads = []

    # Section for MQTT connections
    mqtt_sections = [sec for sec in cparser.sections() if sec.startswith('mqtt')]
    for sec_name in mqtt_sections:
        logger.info('creating MQTT conection')
        mqtt_config = cparser[sec_name]
        if mqtt_config.getboolean('enabled', True):
            q_w = queue.Queue()
            ts = create_mqtt_workers(q_w, mqtt_config)
            working_qs.append(q_w)
            joinable_threads.extend(ts)
        else:
            logger.info('MQTT section %s disabled', sec_name)

    # Section for files
    file_sections = [sec for sec in cparser.sections() if sec.startswith('file')]
    for sec_name in file_sections:
        logger.info('Creating file output')
        sec = cparser[sec_name]
        if sec.getboolean('enabled', True):
            file_config = OtherConf()
            file_config.dirname = sec.get('dirname', '/var/lib/pysqm')
            file_config.format = sec.get('format')
            file_config.interval = sec.getfloat('interval', 300.0)
            file_config.devconf = photo_dev.static_conf()
            file_config.location = loc_conf

            q_w = queue.Queue()
            ts = create_file_writer_workers(q_w, file_config)
            working_qs.append(q_w)
            joinable_threads.extend(ts)
        else:
            logger.info('file section %s disabled', sec_name)

    # reader queue
    q_reader = queue.Queue()

    # Send data to workers
    # basically, write-to-file and mqtt
    consd = threading.Thread(
        name='splitter',
        target=splitter,
        args=(q_reader, working_qs)
    )
    consd.start()
    joinable_threads.append(consd)

    all_readers = []

    # starting only one reader
    # Preliminary configuration here
    readerconf['tz'] = pytz.timezone(loc_conf.timezone)

    # This thread ends in exit_event
    reader = threading.Thread(
        target=read_photometer_timed,
        name=f'photo_reader_{photo_dev.name}',
        args=(photo_dev, q_reader, readerconf, exit_event, error_event)
    )
    reader.start()
    all_readers.append(reader)

    for t in joinable_threads:
        t.join()

    for t in all_readers:
        t.join()

    # Ending main thread
    # Timer threads must be "cancel()" instead
    for t in threading.enumerate():
        if isinstance(t, threading.Timer):
            logger.debug('cancel timer {}'.format(t.name))
            t.cancel()

    if error_event.is_set():
        exit_code = 1

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
