
import threading
import datetime
import re
import queue
import time
import signal
import sys
import json
import logging
import argparse
import configparser


import paho.mqtt.client as mqtt


HALF_S = datetime.timedelta(seconds=0.5)


MEASURE_RE = re.compile(br"""
                \s* # Skip whitespace
                (?P<cmd>r) # Command
                ,\s*
                (?P<sky_brightness>\d*.\d*)m
                ,\s*
                (?P<freq_sensor>\d*)Hz
                ,\s*
                (?P<ticks_uC>\d*)c
                ,\s*
                (?P<period_sensor>\d*.\d*)s
                ,\s*
                (?P<temp_sensor>\d*.\d*)C
                """
               , re.VERBOSE)

CALIB_RE = re.compile(br"""
                \s* # Skip whitespace
                (?P<cmd>c) # Command
                ,\s*
                (?P<light_cal>\d*.\d*)m
                ,\s*
                (?P<dark_period>\d*.\d*)s
                ,\s*
                (?P<light_cal_temp>\d*.\d*)C
                ,\s*
                (?P<off_ref>\d*.\d*)m
                ,\s*
                (?P<dark_cal_temp>\d*.\d*)C
                """
               , re.VERBOSE)

META_RE = re.compile(br"""
                \s* # Skip whitespace
                (?P<cmd>i) # Command
                ,\s*
                (?P<protocol_number>\d*)
                ,\s*(?P<model_number>\d*),\s*
                (?P<feature_number>\d*),\s*(?P<serial_number>\d*)
                """
               , re.VERBOSE)




class SQMTest:
    def __init__(self):
        self.ix = b'i,00000004,00000003,00000023,00002142\r\n'
        self.cx = b'c,00000019.84m,0000151.517s, 022.2C,00000008.71m, 023.2C\r\n'
        self.rx = b'r, 19.29m,0000000002Hz,0000277871c,0000000.603s, 029.9C\r\n'

        self.protocol_number = 0
        self.model_number = 0
        self.feature_number = 0
        self.serial_number = 0
        self.calibration = 0

    def read_metadata(self):
        return self.ix

    def process_metadata(self, msg):
        match = META_RE.match(msg)
        if match:
            self.protocol_number = int(match.group('protocol_number'))
            self.model_number = int(match.group('model_number'))
            self.feature_number = int(match.group('feature_number'))
            self.serial_number = int(match.group('serial_number'))
        else:
            raise ValueError

    def init_metadata(self):
        msg = self.read_metadata()
        self.process_metadata(msg)

    def read_calibration(self):
        return self.cx

    def process_calibration(self, msg):
        match = CALIB_RE.match(msg)
        if match:
            self.calibration = float(match.group('light_cal'))
            return {'light_cal': self.calibration}
        else:
            raise ValueError

    def read_data(self):
        return self.rx

    def process_data(self, msg):
        m = MEASURE_RE.match(msg)
        if m:
            result = {}
            result['mode'] = 'data'
            result['cmd'] = m.group('cmd').decode('utf-8')
            result['sky_brightness'] =  float(m.group('sky_brightness'))
            result['freq_sensor'] = int(m.group('freq_sensor'))
            result['period_sensor'] = float(m.group('period_sensor'))
            result['temp_sensor'] = float(m.group('temp_sensor'))
            return result
        else:
            raise ValueError


def signal_handler(signal, frame, exit_event):
    exit_event.set()


def main():
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger('pysqml')
    logger.info('something, starting')

    exit_event = threading.Event()

    def s_h(s, f):
        return signal_handler(s, f, exit_event)

    signal.signal(signal.SIGINT, s_h)

    sqmtest1 = SQMTest()
    sqmtest2 = SQMTest()

    # producers = [(producer1, sqmtest1), (producer1, sqmtest2)]
    producers = [(producer1, sqmtest1)]
    # consumers = [(consumer1, None), (consumer2, None)]
    consumers = [(consumer1, None)]

    qus = [queue.Queue() for _ in consumers]
    allt = []

    for i, (producer, dev) in enumerate(producers):
        t = threading.Thread(target=producer, args=(qus, exit_event, dev))
        t.start()
        allt.append(t)

    for i, (consumer, args) in enumerate(consumers):
        t = threading.Thread(target=consumer, args=(qus[i],))
        t.start()
        allt.append(t)

    for th in allt:
        logger.debug('join-1')
        th.join()
        logger.debug('join-2')

    logger.info('finish main thread')


def producer1(qus, exit_event, sqmdev):
    from configS import SQM_CONFIG
    idx = 0
    thisth = threading.current_thread()
    logger = logging.getLogger('pysqml')
    logger.info('starting {}'.format(thisth.name))
    do_exit = False

    sqmdev.init_metadata()

    # Read calibration
    data = sqmdev.read_calibration()
    sqmdev.process_calibration(data)
    mac = sqmdev.serial_number
    mm = dict(name=SQM_CONFIG['name'], mac=mac, calib=sqmdev.calibration, rev=1, chan=SQM_CONFIG['channel'], mode='id')

    for qu in qus:
        qu.put(mm)

    do_exit = exit_event.wait(timeout=2)

    while not do_exit:
        data = sqmdev.read_data()
        msg = sqmdev.process_data(data)
        logger.debug('data is {}'.format(data))

        for qu in qus:
            qu.put(msg)
        idx += 1
        do_exit = exit_event.wait(timeout=5)

        if idx > 3:
            do_exit = True

    logger.info('end producer thread')
    logger.info('signalling consumers to end')
    for qu in qus:
        qu.put(None)


def consumer1(qu):
    from configS import SQM_CONFIG
    thisth = threading.current_thread()
    logger = logging.getLogger('pysqml')
    logger.info('starting {}'.format(thisth.name))

    client = mqtt.Client()
    logger.info('open MQTT connection with {}'.format(SQM_CONFIG['hostname']))
    client.username_pw_set(SQM_CONFIG['username'], password=SQM_CONFIG['password'])
    client.connect(SQM_CONFIG['hostname'], 1883, 60)
    client.loop_start()

    do_work = True
    while do_work:
        item = qu.get()
        if item is None:
            do_work = False
        else:
            do_work1(client, item)

        #            logger.debug('publish, response {}'.format(response))
        qu.task_done()
    logger.info('end MQTT consumer thread')


def do_work1(client, msg):
    from configS import SQM_CONFIG

    publish_topic = 'STARS4ALL/{}/reading'.format(SQM_CONFIG['channel'])

    if 'mode' in msg:
        if msg['mode'] == 'id':
            del msg['mode']
            spayload = json.dumps(msg)
            response = client.publish(SQM_CONFIG['register_topic'], spayload)
            print('register, payload', spayload)
            print('register, response', response)
        elif msg['mode'] == 'data':
            del msg['mode']

            payload = dict(seq=0, name=SQM_CONFIG['name'], freq=0.0, mag=0.0, tamb=0.0, tsky=0.0, rev=1)
            seq = 10
            now = datetime.datetime.utcnow()
            payload['seq'] = seq
            # 'freq_sensor': 15370, 'period_sensor': 0.0,
            payload['freq'] = msg['period_sensor']
            payload['mag'] = msg['sky_brightness']
            payload['tamb'] = msg['temp_sensor']
            # payload['tstamp'] = now.isoformat()
            # round to nearest second
            payload['tstamp'] = (now + HALF_S).strftime("%Y-%m-%dT%H:%M:%S")
            spayload = json.dumps(payload)
            response = client.publish(publish_topic, spayload, qos=0)
            print('publish, response', response)


def consumer2(qu):
    logger = logging.getLogger('pysqml')
    thisth = threading.current_thread()
    logger.info('starting {}'.format(thisth.name))
    with open('file.txt', 'a') as fd:
        while True:
            item = qu.get()
            if item is None:
                logger.info('end consumer2 thread')
                qu.task_done()
                break
            do_work2(fd, item)
            qu.task_done()


def do_work2(fd, item):
    fd.write('{}\n'.format(item))


def main_no_th():

    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger('pysqml')
    logger.info('something, starting')

    sqmtest1 = SQMTest()

    # producers = [(producer1, sqmtest1), (producer1, sqmtest2)]
    # producers = [(producer1, sqmtest1)]
    # consumers = [(consumer1, None), (consumer2, None)]
    # consumers = [(consumer1, None)]

    logger.info('finish main')


def reader(sqmdev):

    idx = 0
    logger = logging.getLogger('pysqml')
    do_exit = False

    sqmdev.init_metadata()

    # Read calibration
    data = sqmdev.read_calibration()
    sqmdev.process_calibration(data)
    mac = sqmdev.serial_number
    mm = dict(name='name', mac=mac, calib=sqmdev.calibration, rev=1, chan='', mode='id')

    yield mm

    while not do_exit:
        data = sqmdev.read_data()
        msg = sqmdev.process_data(data)
        logger.debug('data is {}'.format(data))
        yield msg
        idx += 1
        # do_exit = exit_event.wait(timeout=5)
        time.sleep(seconds=5)

        if idx > 3:
            do_exit = True


def producer1(qus, exit_event, sqmdev):
    from configS import SQM_CONFIG
    idx = 0
    thisth = threading.current_thread()
    logger = logging.getLogger('pysqml')
    logger.info('starting {}'.format(thisth.name))
    do_exit = False

    sqmdev.init_metadata()

    # Read calibration
    data = sqmdev.read_calibration()
    sqmdev.process_calibration(data)
    mac = sqmdev.serial_number
    mm = dict(name=SQM_CONFIG['name'], mac=mac, calib=sqmdev.calibration, rev=1, chan=SQM_CONFIG['channel'], mode='id')

    for qu in qus:
        qu.put(mm)
    
    do_exit = exit_event.wait(timeout=2)

    while not do_exit:
        data = sqmdev.read_data()
        msg = sqmdev.process_data(data)
        logger.debug('data is {}'.format(data))

        for qu in qus:
            qu.put(msg)
        idx += 1
        do_exit = exit_event.wait(timeout=5)

        if idx > 3: 
            do_exit = True

    logger.info('end producer thread')
    logger.info('signalling consumers to end')
    for qu in qus:
        qu.put(None)


def consumer1(qu):
    from configS import SQM_CONFIG
    thisth = threading.current_thread()
    logger = logging.getLogger('pysqml')
    logger.info('starting {}'.format(thisth.name))

    client = mqtt.Client()
    logger.info('open MQTT connection with {}'.format(SQM_CONFIG['hostname']))
    client.username_pw_set(SQM_CONFIG['username'], password=SQM_CONFIG['password'])
    client.connect(SQM_CONFIG['hostname'], 1883, 60)
    client.loop_start()

    do_work = True
    while do_work:
        item = qu.get()
        if item is None:
            do_work = False
        else:
            do_work1(client, item)

#            logger.debug('publish, response {}'.format(response))
        qu.task_done()
    logger.info('end MQTT consumer thread')


def do_work1(client, msg):
    from configS import SQM_CONFIG

    publish_topic = 'STARS4ALL/{}/reading'.format(SQM_CONFIG['channel'])

    if 'mode' in msg:
        if msg['mode'] == 'id':
            del msg['mode']
            spayload = json.dumps(msg)
            response = client.publish(SQM_CONFIG['register_topic'], spayload)
            print('register, payload', spayload)
            print('register, response', response)
        elif msg['mode'] == 'data':
            del msg['mode']

            payload = dict(seq=0, name=SQM_CONFIG['name'], freq=0.0, mag=0.0, tamb=0.0, tsky=0.0, rev=1)
            seq = 10
            now = datetime.datetime.utcnow()
            payload['seq'] = seq
            # 'freq_sensor': 15370, 'period_sensor': 0.0,
            payload['freq'] = msg['period_sensor']
            payload['mag'] = msg['sky_brightness']
            payload['tamb'] = msg['temp_sensor']
            # payload['tstamp'] = now.isoformat()
            # round to nearest second
            payload['tstamp'] = (now + HALF_S).strftime("%Y-%m-%dT%H:%M:%S")
            spayload = json.dumps(payload)
            response = client.publish(publish_topic, spayload, qos=0)
            print('data, payload', spayload)
            print('publish, response', response)


def consumer2(qu):
    logger = logging.getLogger('pysqml')
    thisth = threading.current_thread()
    logger.info('starting {}'.format(thisth.name))
    with open('file.txt', 'a') as fd:
        while True:
            item = qu.get()
            if item is None:
                logger.info('end consumer2 thread')
                qu.task_done()
                break
            do_work2(fd, item)
            qu.task_done()
    

def do_work2(fd, item):
    fd.write('{}\n'.format(item))


import logging
import time

import re

import numpy as np

# Default, to ignore the length of the read string.
CAL_LEN = None
META_LEN = None
DATA_LEN = None


def other_main():
    import paho.mqtt.client as mqtt
    import json
    import pytz
    import datetime
    from configS import SQM_CONFIG

    print('init')
    sqm = SQMLU('/dev/ttyUSB0')
    print(sqm.serial_number)
    print('done')

    tz = pytz.utc

    publish_topic = 'STARS4ALL/{}/reading'.format(SQM_CONFIG['channel'])
    mac = sqm.serial_number

    client = mqtt.Client()
    client.username_pw_set(SQM_CONFIG['username'], password=SQM_CONFIG['password'])
    client.connect(SQM_CONFIG['hostname'], 1883, 60)
    client.loop_start()

    # register on power up
    payload = dict(name=SQM_CONFIG['name'], mac=mac, calib=sqm.calibration, rev=1, chan=SQM_CONFIG['channel'])
    spayload = json.dumps(payload)
    response = client.publish(SQM_CONFIG['register_topic'], spayload)
    print('register, payload', spayload)
    print('register, response', response)

    seq = 1
    timeout = 60
    payload = dict(seq=0, name=SQM_CONFIG['name'], freq=0.0, mag=0.0, tamb=0.0, tsky=0.0, rev=1)
    half_s = datetime.timedelta(seconds=0.5)
    while True:
        # now = datetime.datetime.now(tz=pytz.utc)
        now = datetime.datetime.utcnow()
        msg = sqm.read_data()

        print('message is:', msg)
        now.isoformat()
        payload['seq'] = seq
        # 'freq_sensor': 15370, 'period_sensor': 0.0,
        payload['freq'] = msg['period_sensor']
        payload['mag'] = msg['sky_brightness']
        payload['tamb'] = msg['temp_sensor']
        # payload['tstamp'] = now.isoformat()
        # round to nearest second
        payload['tstamp'] = (now + half_s).strftime("%Y-%m-%dT%H:%M:%S")
        spayload = json.dumps(payload)

        print('payload is:', spayload)
        response = client.publish(publish_topic, spayload, qos=0)
        print('publish, response', response)

        seq += 1
        time.sleep(timeout)

    # client.loop_stop()


if __name__ == '__main__':

    main()

