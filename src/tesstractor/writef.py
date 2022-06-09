#
# Copyright 2018-2022 Universidad Complutense de Madrid
#
# This file is part of tesstractor
#
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSE.txt
#


import logging
import pkgutil
import datetime
import glob
import os.path
import queue

import pytz


_logger = logging.getLogger(__name__)


# FIXME: simplify this
IDA_TMPL = {
    'TESS': 'IDA-TESS-template.tpl',
    'TESS-R': 'IDA-TESS-template.tpl',
    'TESSv2': 'IDA-TESS-template.tpl',
    'SQM': 'IDA-SQM-template.tpl',
    'SQM-LU': 'IDA-SQM-template.tpl',
    'SQM-TEST': 'IDA-SQM-template.tpl'
}


class TimeInterval:
    def __init__(self, min_val, max_val):
        self.min_val = min_val
        self.max_val = max_val

    def in_co(self, dt):

        if self.min_val <= dt < self.max_val:
            return True
        else:
            return False

    def in_oc(self, dt):
        if self.min_val < dt <= self.max_val:
            return True
        else:
            return False


class TimedDailyRotator:
    def __init__(self, when):
        self.when = when
        # self.interval = interval
        self.interval = datetime.timedelta(days=1.0)

    def in_interval(self, dt):
        ctime = dt.time()
        cdate = dt.date()

        lim = datetime.datetime.combine(cdate, self.when)
        if ctime < self.when:
            b = lim
            a = lim - self.interval
        else:
            a = lim
            b = lim + self.interval
        return TimeInterval(a, b)


def calc_filename(now, name):
    fname_tmpl = '{date:%Y%m%d_%H%M%S}_{name}.dat'
    return fname_tmpl.format(date=now, name=name)


def init_file(filename, insconf, locconf):
    model = insconf.model
    tmpl_path = IDA_TMPL[model]
    tmpl_b = pkgutil.get_data('tesstractor', tmpl_path)
    template_string = tmpl_b.decode('utf-8')
    with open(filename, 'w') as fd:
        sus = template_string.format(instrument=insconf, location=locconf)
        print(sus[:-1], end='', file=fd)


def startup(time_interval, name, dirname):

    candidates = []
    glob_pattern = '????????_??????_{}.dat'.format(name)
    for f in glob.glob(os.path.join(dirname, glob_pattern)):
        # A RE would be more general?
        g = os.path.basename(f)
        r = g.split('_')
        rr = '_'.join(r[:2])
        mm = datetime.datetime.strptime(rr, "%Y%m%d_%H%M%S")
        candidates.append((g, mm))
    candidates.sort(reverse=True)

    # print(candidates)
    # check most recent
    for cnd in candidates:
        fname, dt = cnd
        # TODO: we are checking all files here
        # but they are sorted, so less checks
        # are required
        if dt > time_interval.max_val:
            # This file is in the future, weird:
            continue

        if time_interval.in_oc(dt):
            create = False
            filename = fname
            break
        else:
            # No candidates
            create = True
            filename = None
            break
    else:
        # No candidates
        create = True
        filename = None

    return create, filename


def consumer_write_file(intput_q: queue.Queue, config):
    """Thread to manage file writing"""
    _logger.info('starting file writer consumer')

    # Open the correct file, create a new one if
    # it doesn't exist
    ref_dt = datetime.datetime.now()
    _logger.debug('current local time, %s', ref_dt)
    # directory with logs

    _logger.debug('directory with previous files, %s', config.dirname)

    _logger.debug('interval of valid logs')
    rot = TimedDailyRotator(
        when=datetime.time(hour=12, minute=0, second=0)
    )
    valid_inter = rot.in_interval(ref_dt)

    last_change = valid_inter.min_val
    next_change = valid_inter.max_val
    _logger.debug('from %s upto %s', last_change, next_change)

    insconf = config.devconf

    create, valid_fname = startup(valid_inter, insconf.name, config.dirname)

    if create:
        valid_fname = calc_filename(ref_dt, name=insconf.name)
        _logger.debug('valid file not found')
        _logger.debug('create %s', valid_fname)
        init_file(
            os.path.join(config.dirname, valid_fname),
            insconf,
            config.location
        )
    else:
        _logger.debug('valid file is %s', valid_fname)

    while True:
        _logger.debug('enter thread loop')
        payload = intput_q.get()
        if payload:
            # We are not going to write this to file anyway
            if payload['cmd'] == 'id':
                continue

            _logger.debug(f'got (w) payload {payload}')
            # Add local time to payload
            payload = update_p(payload)
            #
            # Verify the file is correct before writing
            # if not, create a new one
            now_local = payload['tstamp_local']
            now_local_n = now_local.replace(tzinfo=None)
            if now_local_n >= next_change:
                _logger.debug('read time is after scheduled time change')
                _logger.debug('create new file')
                _logger.debug('compute next change')
                valid_inter = rot.in_interval(now_local_n)
                next_change = valid_inter.max_val
                valid_fname = calc_filename(now_local_n, name=insconf.name)
                init_file(
                    os.path.join(config.dirname, valid_fname),
                    insconf,
                    config.location
                )
            _logger.debug('write to file')
            write_to_file(payload, config.dirname, valid_fname)
            intput_q.task_done()
        else:
            _logger.info('end file writer consumer thread')
            # other.client.loop_stop()
            break


def update_p(payload):
    """Update payload with tstamp_local"""
    now = payload['tstamp']
    local_tz = payload['localtz']
    now_utc = pytz.utc.localize(now)
    now_local = now_utc.astimezone(local_tz)
    payload['tstamp_local'] = now_local
    return payload


def write_to_file(payload, dirname, filename):
    """Write payload to file"""
    payload['tstamp_str'] = payload['tstamp'].isoformat('T', timespec='milliseconds')
    payload['tstamp_local_str'] = payload['tstamp_local'].replace(tzinfo=None).isoformat('T', timespec='milliseconds')
    # m.isoformat('T', timespec='milliseconds')
    line_tpl = "{tstamp_str};{tstamp_local_str};{temp_ambient:.2f};{temp_sky:.2f};{freq_sensor};{magnitude:.2f};{zero_point}"
    with open(os.path.join(dirname, filename), 'a') as fd:
        if payload['cmd'] == 'r':
            if 'temp_ambient' not in payload:
                payload['temp_ambient'] = 0.0
            if 'temp_sky' not in payload:
                payload['temp_sky'] = 0.0
            msg = line_tpl.format(**payload)
            print(msg, file=fd)
    return 0
