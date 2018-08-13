#
# Copyright 2018 Universidad Complutense de Madrid
#
# This file is part of pysqm-lite
#
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSE.txt
#


import logging
import pkgutil
import datetime

import pytz


_logger = logging.getLogger(__name__)

HALF_DAY = datetime.timedelta(days=0.5)


def consumer_write_file(q, other):
    _logger.info('starting file writer consumer')

    while True:
        payload = q.get()
        if payload:
            _logger.debug('got (w) payload %s', payload)
            res = write_to_file_2(payload)
            _logger.debug('server says %s', res)
            q.task_done()
        else:
            _logger.info('end file writer consumer thread')
            # other.client.loop_stop()
            break


def write_to_file(payload):
    _logger.debug('write payload %s to file', payload)
    with open('dum.txt', 'a') as fd:
        fd.write('%{}'.format(payload))
    return 0


def calc_filename(now):
    now_h = now - HALF_DAY
    # fname_tmpl = '{date:%Y%m%d_%H%M%S}_{name}.dat'
    fname_tmpl = '{date:%Y%m%d}_{name}.dat'
    return fname_tmpl.format(date=now_h, name='somename')


class InstrumentConf:
    name = 'somename'
    filter = 'b'
    azimuth = 0.0
    altitude = 0.0
    model = 'model'
    fov = 'fov'
    mac_address = 'xxx'
    firmware = 'firmware'
    cover_offset = 0
    zero_point = 29


class LocationConf:
    contact_name = 'Sergio Pascual'
    organization = 'UCM'
    location = 'location'
    province = 'province'
    country = 'ES'
    site = 'site'
    latitude = 20.000
    longitude = 45.0000
    elevation = 203.4
    timezone = 'TZ'


def write_to_file_2(payload):
    # try file
    now = payload['tstamp']
    local_tz = payload['localtz']
    now_utc = pytz.utc.localize(now)
    now_local = now_utc.astimezone(local_tz)
    payload['tstamp_local'] = now_local

    filename = calc_filename(now_local)

    # os.remove(filename)
    a = InstrumentConf()
    b = LocationConf()
    try:
        open(filename)
    except FileNotFoundError:
        _logger.debug('file not found, create')
        tmpl_b = pkgutil.get_data('pysqml', 'IDA-template.tpl')
        template_string = tmpl_b.decode('utf-8')
        with open(filename, 'w') as fd:
            sus = template_string.format(instrument=a, location=b)
            print(sus[:-1], end='', file=fd)
    payload['tstamp_str'] = payload['tstamp'].isoformat('T', timespec='milliseconds')
    payload['tstamp_local_str'] = payload['tstamp_local'].replace(tzinfo=None).isoformat('T', timespec='milliseconds')
    # m.isoformat('T', timespec='milliseconds')
    line_tpl = "{tstamp_str};{tstamp_local_str};0;{temp_sensor};{freq_sensor};{sky_brightness};0"
    with open(filename, 'a') as fd:
        print(payload)
        if payload['cmd'] == 'r':
            msg = line_tpl.format(**payload)
            print(msg, file=fd)
    return 0