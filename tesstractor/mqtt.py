#
# Copyright 2018-2019 Universidad Complutense de Madrid
#
# This file is part of tessreader
#
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSE.txt
#

import datetime
import logging
import json

import paho.mqtt.client as mqtt


_HALF_S = datetime.timedelta(seconds=0.5)

_logger = logging.getLogger(__name__)


def consumer_mqtt(q, other):
    _logger.info('starting MQTT consumer')
    try:
        other.connect()
        other.client.loop_start()

        while True:
            payload = q.get()
            if payload:
                _logger.debug('got payload %s', payload)
                res = other.do_work1(payload)
                _logger.debug('server says %s', res)
                q.task_done()
            else:
                _logger.info('end MQTT consumer thread')
                other.client.loop_stop()
                break
    except IOError:
        _logger.exception('connecting to MQTT server')


class MqttConsumer:
    def __init__(self, config):
        self.client = mqtt.Client()
        self.config = config
        self.seq = 1

        self.MSG = '"seq": {seq}, "name": "{name}", "freq": {freq:.3f}, "mag": {mag:.2f},' \
                   ' "tamb": {tamb:.1f}, "tsky": {tsky:.1f}, "rev": {rev}, "tstamp": "{tstamp}"'
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
            _logger.debug('enter register')
            # reset sequence number
            self.seq = 1
            payload = dict(msg)
            del payload['cmd']
            del payload['localtz']
            if 'tstamp_local' in payload:
                del payload['tstamp_local']
            # round to nearest second
            payload['tstamp'] = (msg['tstamp'] + _HALF_S).strftime("%FT%T")
            payload['chan'] = self.config['publish_topic'].format(name=msg['name'])

            spayload = json.dumps(payload)
            _logger.debug('sending register msg %s', spayload)
            response = self.client.publish(self.config['register_topic'], spayload)
            return response
        elif msg['cmd'] == 'r':
            _logger.debug('enter publish')
            payload = dict(seq=self.seq, name='unknown', freq=0.0, mag=0.0, tamb=99.0, tsky=99.0, rev=1)
            self.seq += 1
            # This may depend on the device
            payload['name'] = msg['name']
            payload['freq'] = msg['freq']
            payload['mag'] = msg['magnitude']
            if 'temp_ambient' in msg:
                payload['tamb'] = msg['temp_ambient']
            if 'temp_sky' in msg:
                payload['tsky'] = msg['temp_sky']
            # round to nearest second
            payload['tstamp'] = (msg['tstamp'] + _HALF_S).strftime("%FT%T")

            spayload = self.MSG.format(**payload)
            spayload = '{{{}}}'.format(spayload)
            # With this I can't control numeric precision
            # spayload = json.dumps(payload)
            publish_topic = self.config['publish_topic'].format(**payload)
            response = self.client.publish(publish_topic, spayload, qos=0)
            _logger.debug('sending data %s', spayload)
            return response
        else:
            raise ValueError('MQTT.do_work1, msg cmd is unknown')
