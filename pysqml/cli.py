#
# Copyright 2018 Universidad Complutense de Madrid
#
# This file is part of pysqm-lite
#
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSE.txt
#

import threading
import datetime
import queue
import signal
import logging

import serial
import pytz
import attr
import tzlocal

from pysqml.sqm import SQMTest, SQMLU, filter_buffer
import pysqml.mqtt as mqtt
import pysqml.writef


# FIXME: This is applied in two places
_HALF_S = datetime.timedelta(seconds=0.5)

_logger = logging.getLogger(__name__)


def signal_handler_function(signum, frame, exit_event):
    exit_event.set()


def read_photometer_timed(sqm, q, exit_event):
    thisth = threading.current_thread()
    _logger.info('starting {} thread'.format(thisth.name))
    seq = 0

    buffer = []
    nsamples = 6
    timeout = 10

    # initialice connection. read metadata and calibration

    try:
        sqm.read_metadata()
        # Read calibration
        sqm.read_calibration()

        mac = sqm.serial_number
        now = datetime.datetime.utcnow()
        local_tz = tzlocal.get_localzone()

        payload_init = dict(
            name=sqm.name,
            mac=mac,
            calib=sqm.calibration,
            rev=1,
            chan="unknown",
            cmd='id',
            tstamp=now,
            localtz=local_tz
        )

        q.put(payload_init)

        do_exit = exit_event.wait(timeout=2)

        while not do_exit:
            now = datetime.datetime.utcnow()
            local_tz = tzlocal.get_localzone()
            #now_utc = pytz.utc.localize(now)
            #now_local = now_utc.astimezone(local_tz)
            msg = sqm.read_data()
            payload = dict(msg)
            payload['tstamp'] = now
            payload['localtz'] = local_tz
            payload['name'] = sqm.name

            buffer.append(payload)
            if len(buffer) >= nsamples:
                # do average
                avg = filter_buffer(buffer)
                avg['seq'] = seq
                # reset buffer
                buffer = []
                q.put(avg)
                seq += 1
            do_exit = exit_event.wait(timeout=timeout)

    finally:
        _logger.info('end producer thread')
        _logger.info('signalling producers to end')
        exit_event.set()
        _logger.info('signalling consumers to end')
        q.put(None)


def conductor(q, qs):
    thisth = threading.current_thread()
    _logger.info('starting {} thread'.format(thisth.name))
    while True:
        payload = q.get()
        q.task_done()
        for wq in qs:
            wq.put(payload)
        if payload is None:
            _logger.info('end conductor thread')
            break


def simple_consumer(q, other):
    _logger.info('starting simple_consumer thread')
    while True:
        payload = q.get()
        if payload:
            print(payload)
            q.task_done()
        else:
            _logger.info('end simple_consumer thread')
            break


def build_dev_from_ini(section):
    tipo = section.get('type', 'test')
    if tipo == 'test':
        return SQMTest()
    else:
        name = section.get('name')
        port = section.get('port', '/dev/ttyUSB')
        baudrate = section.get('baudrate', 115200)
        conn = serial.Serial(port, baudrate, timeout=2)
        sqm = SQMLU(conn, name)
        return sqm


class Conf:
    pass


def build_consumers_from_ini(conf):

    # Read location first
    loc_conf = build_location_from_ini(conf)

    otherconf = Conf()
    otherconf.location = loc_conf
    otherconf.dirname = conf['file']['dirname']

    # valid values: mqtt, simple, file
    consumers = []
    mqtt_sections = [sec for sec in conf.sections() if sec.startswith('mqtt')]
    for sec in mqtt_sections:
        mqtt_config = conf[sec]
        if mqtt_config.getboolean('enabled', True):
            other_mqtt = mqtt.MqttConsumer(mqtt_config)
            consumers.append((mqtt.consumer_mqtt, other_mqtt))

    simple_sections = [sec for sec in conf.sections() if sec.startswith('simple')]
    for _ in simple_sections:
        consumers.append((simple_consumer, None))

    file_sections = [sec for sec in conf.sections() if sec.startswith('file')]
    for sec in file_sections:
        consumers.append((pysqml.writef.consumer_write_file, otherconf))

    return consumers

def build_location_from_ini(conf):
    location_sec = conf['location']

    print(location_sec)
    print(conf.options('location'))
    loc = LocationConf()
    for key in location_sec:
        setattr(loc, key, location_sec[key])

    return loc


ini_defaults = {
    'file': {
        'dirname': '/var/lib/pysqm',
    },
    'provider': {
        'contact_name': 'unknwon',
        'organization': 'unkwnon'
    },
    'location': {
        'location': 'unknwon',
        'province': 'unknwon',
        'country': 'unknwon',
        'site': 'unknwon',
        #
        'latitude': 0.0,
        'longitude': 0.0,
        'elevation': 0.0,
        #
        'timezone': 'UTC'
    }
}

@attr.s
class LocationConf:
    contact_name = attr.ib(default='')
    organization = attr.ib(default='')
    location = attr.ib(default='')
    province = attr.ib(default='')
    country = attr.ib(default='')
    site = attr.ib(default='')

    latitude = attr.ib(converter=float, default=0.0)
    longitude = attr.ib(converter=float, default=0.0)
    elevation = attr.ib(converter=float, default=0.0)

    timezone = attr.ib(default='UTC')


def main(args=None):
    import sys
    import argparse
    import configparser

    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser()
    parser.add_argument('--dirname')
    parser.add_argument('-c', '--config')

    pargs = parser.parse_args(args=args)
    print(pargs)
    cparser = configparser.ConfigParser()

    cparser.read_dict(ini_defaults)
    if pargs.config:
        cparser.read(pargs.config)

    ini_overrides = {
        'file': {}
    }
    if pargs.dirname is not None:
        ini_overrides['file']['dirname'] = pargs.dirname

    cparser.read_dict(ini_overrides)

    sqm_sections = [sec for sec in cparser.sections() if sec.startswith('sqm_')]
    sqmlist = [build_dev_from_ini(cparser[sec]) for sec in sqm_sections]

    consumers = build_consumers_from_ini(cparser)

    ncons = len(consumers)
    nsqm = len(sqmlist)

    if nsqm == 0:
        logger.warning('No SQM devices defined. Exit')
        sys.exit(1)

    if ncons == 0:
        logger.warning('No data consumers defined. Exit')
        sys.exit(1)

    logger.info('pysqml-lite, starting')

    exit_event = threading.Event()

    def signal_handler(signum, frame):
        return signal_handler_function(signum, frame, exit_event)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # producer queue
    q_prod = queue.Queue()

    # Working queues
    q_cons = [queue.Queue() for _ in range(ncons)]

    consd = threading.Thread(name='manager',
                             target=conductor,
                             args=(q_prod, q_cons)
                             )
    consd.start()

    all_consumers = []

    for idx, (consumer, other) in enumerate(consumers):
        cons = threading.Thread(target=consumer, name='consumer_{}'.format(idx),
                                args=(q_cons[idx], other))
        cons.start()
        all_consumers.append(cons)

    all_readers = []

    for idx, sqm in enumerate(sqmlist):
        reader = threading.Thread(
            target=read_photometer_timed,
            name='sqm_reader_{}'.format(sqm.name),
            args=(sqm, q_prod, exit_event)
        )
        reader.start()
        all_readers.append(reader)

    consd.join()

    for t in all_readers:
        t.join()

    for t in all_consumers:
        t.join()


if __name__ == '__main__':

    main()
