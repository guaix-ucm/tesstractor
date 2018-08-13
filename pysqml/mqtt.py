#
# Copyright 2018 Universidad Complutense de Madrid
#
# This file is part of pysqm-lite
#
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSE.txt
#

import datetime
import logging
import json
import socket

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
            msg['chan'] = msg['name']

            spayload = json.dumps(msg)
            _logger.debug('sending register msg %s', spayload)
            response = self.client.publish(self.config['register_topic'], spayload)
            return response
        elif msg['cmd'] == 'r':
            del msg['cmd']

            payload = dict(seq=0, name='unknown', freq=0.0, mag=0.0, tamb=0.0, tsky=0.0, rev=1)

            payload['seq'] = msg['seq']
            payload['name'] = msg['name']
            payload['freq'] = msg['period_sensor']
            payload['mag'] = msg['sky_brightness']
            payload['tamb'] = msg['temp_sensor']
            # round to nearest second
            payload['tstamp'] = (msg['tstamp'] + _HALF_S).strftime("%FT%T")
            spayload = json.dumps(payload)
            publish_topic = self.config['publish_topic'].format(**payload)
            response = self.client.publish(publish_topic, spayload, qos=0)
            _logger.debug('sending data %s', spayload)
            return response
        else:
            raise ValueError
