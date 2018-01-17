
import threading
import time
import datetime
import queue
import signal
import logging
import json

import serial

from pysqml.sqm import SQMTest, SQMLU

import paho.mqtt.client as mqtt


_HALF_S = datetime.timedelta(seconds=0.5)

_logger = logging.getLogger('pysqml')


def signal_handler_function(signum, frame, exit_event):
    exit_event.set()


def read_photometer(sqm, seq):
    now = datetime.datetime.utcnow()
    msg = sqm.read_data()

    payload = dict(msg)
    payload['seq'] = seq
    payload['tstamp'] = (now + _HALF_S).strftime("%Y-%m-%dT%H:%M:%S")
    return payload


def read_photometer_timed(sqm, q, exit_event):
    thisth = threading.current_thread()
    logger = logging.getLogger('pysqml')
    logger.info('starting {} thread'.format(thisth.name))
    seq = 0
    # FIXME: any exception here should terminate all the threads

    # initialice connection. read metadata and calibration
    sqm.read_metadata()
    # Read calibration
    sqm.read_calibration()

    mac = sqm.serial_number
    payload_init = dict(
        name=sqm.name,
        mac=mac,
        calib=sqm.calibration,
        rev=1,
        chan="unknown",
        cmd='id'
    )

    q.put(payload_init)

    do_exit = exit_event.wait(timeout=2)

    while not do_exit:
        payload = read_photometer(sqm, seq)
        payload['name'] = sqm.name
        q.put(payload)
        seq += 1
        do_exit = exit_event.wait(timeout=5)

    logger.info('end producer thread')
    logger.info('signalling consumers to end')
    q.put(None)


def conductor(q, qs):
    thisth = threading.current_thread()
    logger = logging.getLogger('pysqml')
    logger.info('starting {} thread'.format(thisth.name))
    while True:
        payload = q.get()
        q.task_done()
        for wq in qs:
            wq.put(payload)
        if payload is None:
            logger.info('end conductor thread')
            break


def consumer0(q, other):
    logger = logging.getLogger('pysqml')
    logger.info('s consumer0')
    while True:
        payload = q.get()
        if payload:
            logger.debug('payload0 %s', payload)
            q.task_done()
        else:
            logger.info('end consumer0 thread')
            break


def consumer1(q, other):
    logger = logging.getLogger('pysqml')
    logger.info('s consumer1')
    while True:
        payload = q.get()
        if payload:
            logger.debug('payload1 %s', payload)
            q.task_done()
        else:
            logger.info('end consumer1 thread')
            break


def consumer_mqtt(q, other):
    logger = logging.getLogger('pysqml')
    _logger.info('starting MQTT consumer')

    other.connect()
    other.client.loop_start()

    while True:
        payload = q.get()
        if payload:
            logger.debug('got payload %s', payload)
            res = other.do_work1(payload)
            logger.debug('server says %s', res)
            q.task_done()
        else:
            logger.info('end MQTT consumer thread')
            other.client.loop_stop()
            break


class MqttConsumer:
    def __init__(self, config):
        self.client = mqtt.Client()
        self.config = config

        # logger.info('open MQTT connection with {}'.format(SQM_CONFIG['hostname']))

        self.publish_topic = 'STARS4ALL/{}/reading'.format(self.config['channel'])

    # client.loop_start()

    def connect(self):
        self.client.username_pw_set(
            self.config['username'],
            password=self.config['password']
        )
        _logger.info('open MQTT connection with {}'.format(self.config['hostname']))
        self.client.connect(
            self.config['hostname'],
            1883,
            60
        )

    def do_work1(self, msg):
        if msg['cmd'] == 'id':
            del msg['cmd']
            msg['chan'] = self.config['channel']

            spayload = json.dumps(msg)
            _logger.debug('sending register msg %s', spayload)
            response = self.client.publish(self.config['register_topic'], spayload)
            return response
        elif msg['cmd'] == 'r':
            del msg['cmd']

            payload = dict(seq=0, freq=0.0, mag=0.0, tamb=0.0, tsky=0.0, rev=1)

            now = datetime.datetime.utcnow()
            payload['seq'] = msg['seq']
            # 'freq_sensor': 15370, 'period_sensor': 0.0,
            payload['freq'] = msg['period_sensor']
            payload['mag'] = msg['sky_brightness']
            payload['tamb'] = msg['temp_sensor']
            # payload['tstamp'] = now.isoformat()
            # round to nearest second
            payload['tstamp'] = (now + _HALF_S).strftime("%Y-%m-%dT%H:%M:%S")
            spayload = json.dumps(payload)
            response = self.client.publish(self.publish_topic, spayload, qos=0)
            _logger.debug('sending data %s', spayload)
            return response
        else:
            raise ValueError

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


def build_consumers_from_init(conf):
    # valid values: mqtt,
    consumers = []
    mqtt_sections = [sec for sec in conf.sections() if sec.startswith('mqtt')]
    for sec in mqtt_sections:
        mqtt_config = conf[sec]
        other_mqtt = MqttConsumer(mqtt_config)
        consumers.append((consumer_mqtt, other_mqtt))
    return consumers


def build_comsumer_from_ini(section):
    tipo = section.get('type', 'test')
    if tipo == 'test':
        return SQMTest()
    else:
        name = section.get('name')
        print('name is ', name)
        conn = serial.Serial('/dev/ttyUSB0', 115200, timeout=2)
        sqm = SQMLU(conn, name)
        return sqm


def main(args=None):
    import sys
    import argparse
    import configparser

    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config')

    pargs = parser.parse_args(args=args)

    cparser = configparser.ConfigParser()
    if pargs.config:
        cparser.read(pargs.config)

    sqm_sections = [sec for sec in cparser.sections() if sec.startswith('sqm_')]
    sqmlist = [build_dev_from_ini(cparser[sec]) for sec in sqm_sections]

    consumers = build_consumers_from_init(cparser)

    ncons = len(consumers)
    nsqm = len(sqmlist)

    if nsqm == 0:
        logger.warning('No SQM devices defined. Exit')
        sys.exit(1)

    if ncons == 0:
        logger.warning('No data consumers defined. Exit')
        sys.exit(1)

    # Only 1 SQM is supported for the moment
    sqm = sqmlist[0]

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

    timer = threading.Thread(
        target=read_photometer_timed,
        name='sqm_reader',
        args=(sqm, q_prod, exit_event)
    )
    timer.start()

    consd.join()
    timer.join()
    for t in all_consumers:
        t.join()


if __name__ == '__main__':

    main()
