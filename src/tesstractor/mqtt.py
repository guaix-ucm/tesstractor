#
# Copyright 2018-2024 Universidad Complutense de Madrid
#
# This file is part of tesstractor
#
# SPDX-License-Identifier: GPL-3.0-or-later
# License-Filename: LICENSE.txt
#

import datetime
import logging
import json
import queue

import paho.mqtt.client as mqtt


_HALF_S = datetime.timedelta(seconds=0.5)

_logger = logging.getLogger(__name__)


class MqttConsumer:
    """Handle mqtt connections"""
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

    def do_work(self, msg):
        """Format payload and send it to server"""
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
            payload = dict(seq=self.seq, name='unknown', freq=0.0, mag=0.0, tamb=0.0, tsky=0.0, rev=1)
            self.seq += 1
            # This may depend on the device
            payload['name'] = msg['name']
            payload['freq'] = msg['freq_sensor']
            if 'protocol_revision' in msg:
                payload['rev'] = msg['protocol_revision']
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
            raise ValueError('MQTT.do_work, msg cmd is unknown')


def consumer_mqtt(q: queue.Queue, other: MqttConsumer):
    _logger.info('starting MQTT consumer')
    try:
        other.connect()
        other.client.loop_start()

        while True:
            payload = q.get()
            if payload:
                _logger.debug('got payload %s', payload)
                res = other.do_work(payload)
                _logger.debug('server says %s', res)
                q.task_done()
            else:
                _logger.info('end MQTT consumer thread')
                other.client.loop_stop()
                break
    except IOError:
        _logger.exception('connecting to MQTT server')
