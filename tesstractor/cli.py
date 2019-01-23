#
# Copyright 2018-2019 Universidad Complutense de Madrid
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

import serial
import attr

from tesstractor.sqm import SQMTest, SQMLU
from tesstractor.tess import Tess
import tesstractor.mqtt as mqtt
import tesstractor.writef
import tesstractor.tess


from tesstractor.workers import splitter, simple_buffer, timed_task, read_photometer_timed


def signal_handler_function(signum, frame, exit_event):
    exit_event.set()


class Conf:
    pass


class Other:
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


def build_location_from_ini(conf):
    location_sec = conf['location']

    loc = LocationConf()
    for key in location_sec:
        setattr(loc, key, location_sec[key])

    return loc


def build_dev_from_ini(section):
    model = section.get('model', 'test')
    if model == 'test':
        return SQMTest()
    elif model == 'SQM-LU':
        name = section.get('name')
        port = section.get('port', '/dev/ttyUSB0')
        baudrate = section.getint('baudrate', 115200)
        timeout = section.getfloat('timeout', 2.0)
        conn = serial.Serial(port, baudrate, timeout=timeout)
        photo_dev = SQMLU(conn, name)
        # FIXME: workaround to handle MAC
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
            print('name is none, this should be automatic')
            name='TESS-test'

        photo_dev = tesstractor.tess.TessR(conn, name)
        zero_point = section.getfloat('zero_point', 20.0)
        photo_dev.calibration = zero_point
        # FIXME: workaround to handle MAC
        mac = section.get('mac')
        if mac:
            photo_dev.mac = mac

        return photo_dev
    else:
        raise ValueError('unkown model {}'.format(model))


def create_mqtt_workers(q_worker, mqtt_config):

    otherx = Other()
    #otherx.send_event = send_event

    q_mqtt_in = queue.Queue() # Queue for MQTT
    q_buffer = queue.Queue() # Queue for MQTT buffer

    filter_thread = threading.Thread(target=simple_buffer, name='simple_filter1',
                                     args=(q_worker, q_mqtt_in, q_buffer, otherx))

    interval = mqtt_config.getfloat('interval', 60.0)
    other_mqtt = mqtt.MqttConsumer(mqtt_config)
    consumer_mqtt = threading.Thread(
        target=mqtt.consumer_mqtt, name='mqtt_consumer',
        args=(q_mqtt_in, other_mqtt))

    send_event = None
    timed_buffer = threading.Timer(interval, timed_task, args=(q_buffer, q_mqtt_in, send_event))
    timed_buffer.name = 'timed_buffer_mqtt'

    filter_thread.start()
    timed_buffer.start()
    consumer_mqtt.start()

    return [filter_thread, consumer_mqtt]


def create_file_writer_workers(q_worker, file_config):

    otherx = Other()
    q_file_in = queue.Queue() # Queue for file writer
    q_buffer = queue.Queue()  # Queue for file writer buffer
    send_event = None

    filter_thread = threading.Thread(target=simple_buffer, name='simple_filter2',
                                     args=(q_worker, q_file_in, q_buffer, otherx))


    consumer_file = threading.Thread(target=tesstractor.writef.consumer_write_file, name='consumer_write_file',
                                     args=(q_file_in, file_config))

    interval = file_config.interval
    timed_buffer = threading.Timer(interval, timed_task, args=(q_buffer, q_file_in, send_event))
    timed_buffer.name = 'timed_buffer_file'

    consumer_file.start()
    filter_thread.start()
    timed_buffer.start()

    return [filter_thread, consumer_file]


def main(args=None):
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    logger.info('tesstractor-lite, starting')

    # Register events and signal
    exit_event = threading.Event()
    send_event = threading.Event()

    send_event.clear()

    def signal_handler(signum, frame):
        return signal_handler_function(signum, frame, exit_event)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Parse CLI
    parser = argparse.ArgumentParser()
    parser.add_argument('--dirname')
    parser.add_argument('-c', '--config')

    pargs = parser.parse_args(args=args)
    cparser = configparser.ConfigParser(defaults={'dirname': '/var/lib/pysqm'})

    cparser.read_dict(ini_defaults)
    if pargs.config:
        cparser.read(pargs.config)

    ini_overrides = {
    }
    if pargs.dirname is not None:
        ini_overrides['file'] = {}
        ini_overrides['file']['dirname'] = pargs.dirname

    cparser.read_dict(ini_overrides)

    # FIXME: Here, we should use only the first enabled
    photo_sections = [sec for sec in cparser.sections() if sec.startswith('photometer')]
    photolist = [build_dev_from_ini(cparser[sec]) for sec in photo_sections]

    nsqm = len(photolist)

    if nsqm == 0:
        logger.warning('No devices defined. Exit')
        sys.exit(1)

    photoconf = []
    for photodev in photolist:
        photodev.start_connection()
        photoconf.append(photodev.static_conf())

    photo_dev = photolist[0]

    photo_dev.start_connection()
    loc_conf = build_location_from_ini(cparser)

    # Working queues
    q_cons = []
    # joinable threads
    j_threads = []

    conf = cparser
    mqtt_sections = [sec for sec in conf.sections() if sec.startswith('mqtt')]
    for sec in mqtt_sections:
        mqtt_config = conf[sec]
        if mqtt_config.getboolean('enabled', True):
            q_w = queue.Queue()
            ts = create_mqtt_workers(q_w, mqtt_config)
            q_cons.append(q_w)
            j_threads.extend(ts)

    file_sections = [sec for sec in conf.sections() if sec.startswith('file')]
    for sec_name in file_sections:
        sec = conf[sec_name]
        file_config = Other()
        file_config.dirname = sec.get('dirname', '/var/lib/pysqm')
        file_config.format = sec.get('format')
        file_config.interval = sec.getfloat('interval', 300.0)
        file_config.insconf = photo_dev.static_conf()
        file_config.location = loc_conf

        q_w = queue.Queue()
        ts = create_file_writer_workers(q_w, file_config)
        q_cons.append(q_w)
        j_threads.extend(ts)

    # reader queue
    q_reader = queue.Queue()

    consd = threading.Thread(name='splitter',
                             target=splitter,
                             args=(q_reader, q_cons)
                             )
    consd.start()
    j_threads.append(consd)

    all_readers = []

    # starting only one reader
    reader = threading.Thread(
        target=read_photometer_timed,
        name='photo_reader_{}'.format(photo_dev.name),
        args=(photo_dev, q_reader, exit_event)
    )
    reader.start()
    all_readers.append(reader)

    for t in j_threads:
        t.join()

    for t in all_readers:
        t.join()

    # Ending main thread
    # print('(M) cancelling timers')
    for t in threading.enumerate():
        if isinstance(t, threading.Timer):
            logger.debug('cancel timer {}'.format(t.name))
            t.cancel()


if __name__ == '__main__':
    main()
