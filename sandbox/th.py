from __future__ import print_function


import sqm as sqmmod
from configS import SQM_CONFIG

import configparser
import argparse
import signal

import threading
from queue import Queue

import time
import json
import pytz
import datetime

sample_queue = Queue()

HALF_S = datetime.timedelta(seconds=0.5)


def reader(sqmdev, queue, timeout=6, name='some'):
    seq = 1
    payload = dict(seq=0, name=name, freq=0.0, mag=0.0, tamb=0.0, tsky=0.0, rev=1)
    while True:
        # now = datetime.datetime.now(tz=pytz.utc)
        now = datetime.datetime.utcnow()
        msg = sqmdev.read_data()

        print('message is:', msg)
        now.isoformat()
        payload['seq'] = seq
        # 'freq_sensor': 15370, 'period_sensor': 0.0,
        payload['freq'] = msg['period_sensor']
        payload['mag'] = msg['sky_brightness']
        payload['tamb'] = msg['temp_sensor']
        # payload['tstamp'] = now.isoformat()
        # round to nearest second
        payload['tstamp'] = (now + HALF_S).strftime("%Y-%m-%dT%H:%M:%S")
        spayload = json.dumps(payload)

        #print('payload is:', spayload)
        print('reading')
        # response = client.publish(publish_topic, spayload, qos=0)
        # print('publish, response', response)
        queue.put(payload)
        print('unfinished', queue.unfinished_tasks)
        seq += 1
        time.sleep(timeout)


class StreamMovingAverage(object):
    def __init__(self, size):
        self.size = size
        self.lqueue = Queue()
        for _ in range(size):
            self.lqueue.put(0.0)

        self.nc = 0
        self.pma = 0

    def add(self, value):
        nnc = min(self.size, self.nc + 1)
        # Store our value, will use it later
        last = self.lqueue.get()
        self.lqueue.put(value)
        self.pma = (self.pma * self.nc + value - last) / nnc
        self.nc = nnc
        return self.pma


def worker(queue):

    sma = StreamMovingAverage(5)
    # simpler:
    # r = collections.deque(maxlen=5)
    # r.append(queue.get())
    # return sum(r) / len(r)

    while True:
        if not queue.empty():
            print('doing something')
            payload = queue.get()
            value = payload['mag']
            newval = sma.add(value)
            print(value, newval)
            queue.task_done()
            print('unfinished', queue.unfinished_tasks)

def main():

    def signal_handler(signal, frame):
        print('You pressed Ctrl+C!')

    signal.signal(signal.SIGINT, signal_handler)

    print('init')
    sqm = sqmmod.SQMLU(addr='/dev/ttyUSB0')
    print(sqm.serial_number)
    print('done')

    tz = pytz.utc

    publish_topic = 'STARS4ALL/{}/reading'.format(SQM_CONFIG['channel'])
    mac = sqm.serial_number

    # client = mqtt.Client()
    # client.username_pw_set(SQM_CONFIG['username'], password=SQM_CONFIG['password'])
    # client.connect(SQM_CONFIG['hostname'], 1883, 60)
    # client.loop_start()

    # register on power up
    payload = dict(name=SQM_CONFIG['name'], mac=mac, calib=sqm.calibration, rev=1, chan=SQM_CONFIG['channel'])
    spayload = json.dumps(payload)
    # response = client.publish(SQM_CONFIG['register_topic'], spayload)
    print('register, payload', spayload)
    #print('register, response', response)

    t = threading.Thread(target=reader, args=(sqm, sample_queue, 6, 'some1'), name='reader1')
    t.start()

    w = threading.Thread(target=worker, args=(sample_queue,), name='worker1')
    w.start()


    sample_queue.join()
    print('pass join')


if __name__ == '__main__':

    main()