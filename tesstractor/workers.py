#
# Copyright 2018-2019 Universidad Complutense de Madrid
#
# This file is part of tessreader
#
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSE.txt
#

import datetime
import threading
import logging

import tzlocal
import queue


# FIXME: this is for filter buffer2
# this can be done better
from tesstractor.tess import Tess
from tesstractor.sqm import SQM


filter_buffer_map = {
    'TESS': Tess.filter_buffer2,
    'SQM': SQM.filter_buffer2
}


_logger = logging.getLogger(__name__)

def read_photometer_timed(device, q, exit_event, error_event):
    thisth = threading.current_thread()
    _logger.info('starting {} thread'.format(thisth.name))
    seq = 0

    buffer = []
    nsamples = 5
    exit_check_timeout = 5
    # print('(1)timed_reader, reading every ', timeout, 's')
    # initialice connection. read metadata and calibration

    try:
        # already done by start_connection
        # device.read_metadata()
        # Read calibration
        # device.read_calibration()

        mac = device.serial_number
        now = datetime.datetime.utcnow()
        local_tz = tzlocal.get_localzone()

        payload_init = dict(
            name=device.name,
            model=device.model,
            mac=mac,
            calib=device.calibration,
            rev=1,
            cmd='id',
            tstamp=now,
            localtz=local_tz
        )

        q.put(payload_init)
        # exit after this
        # q.put(None)
        # exit_event.set()
        do_exit = exit_event.wait(timeout=exit_check_timeout)
        tries = 3

        while not do_exit:
            now = datetime.datetime.utcnow()
            local_tz = tzlocal.get_localzone()
            #now_utc = pytz.utc.localize(now)
            #now_local = now_utc.astimezone(local_tz)

            msg = device.read_data(tries=tries)
            if msg is None:
                continue

            # print('(R)timed_reader loop', msg)
            # FIXME: this could be inside read_data
            payload = dict(msg)
            payload['tstamp'] = now
            payload['localtz'] = local_tz
            _logger.debug('payload is {}'.format(payload))
            buffer.append(payload)
            _logger.debug('nsamples is {}'.format(len(buffer)))
            if len(buffer) >= nsamples:
                _logger.debug('averaging {} samples'.format(len(buffer)))
                # print('(R) enough samples', len(buffer))
                # do average
                avg = device.filter_buffer(buffer)
                avg['seq'] = seq
                # reset buffer
                buffer = []
                _logger.debug('buffer avg is {}'.format(avg))
                _logger.debug('reset buffer {}'.format(buffer))
                q.put(avg)
                seq += 1
            do_exit = exit_event.wait(timeout=exit_check_timeout)
    except Exception as ex:
        _logger.debug('exception happend %s', ex)
        error_event.set()
    finally:
        _logger.debug('end read thread')
        _logger.debug('signalling producers to end')
        exit_event.set()
        _logger.debug('signalling consumers to end')
        q.put(None)


def splitter(q, qs):
    thisth = threading.current_thread()
    _logger.debug('starting {} thread'.format(thisth.name))
    while True:
        payload = q.get()
        q.task_done()
        for wq in qs:
            # Sending to all tasks...
            wq.put(payload)
        if payload is None:
            _logger.debug('end {} thread'.format(thisth.name))
            break


def simple_consumer(q, other):
    thisth = threading.current_thread()
    _logger.debug('starting simple_consumer thread, %s', thisth.name)
    while True:
        payload = q.get()
        if payload:
            if payload['cmd'] == 'id':
                print('(C)', thisth.name, 'register options', payload)
                pass
            elif payload['cmd'] == 'r':
                print('(C)', thisth.name, 'data', payload)
                pass
            else:
                print('(=)', thisth.name, 'other', payload)
                pass
            q.task_done()
        else:
            _logger.debug('end %s thread', thisth.name)
            break


def simple_buffer(q_in, q_out, q_buffer, other):
    thisth = threading.current_thread()
    _logger.debug('starting filter buffer thread, %s', thisth.name)
    while True:
        payload = q_in.get()
        if payload:
            if payload['cmd'] == 'id':
                q_out.put(payload)
            elif payload['cmd'] == 'r':
                q_buffer.put(payload)
            else:
                _logger.warning('unknown cmd, %s', payload)
            q_in.task_done()
        else:
            _logger.debug('end %s thread', thisth.name)
            q_out.put(None)
            q_buffer.put(None)
            break


def timed_task(q_in1, q_out, other):

    thisth = threading.current_thread()
    interval = thisth.interval

    _logger.debug('wakeup timer thread, %s', thisth.name)
    # other.set()

    # copy queue in buffer
    buffer = []
    _logger.debug('copy buffer')
    try:
        while True:
            p = q_in1.get_nowait()
            if p is None:
                # None is a signal to exit
                return
            buffer.append(p)
            q_in1.task_done()
    except queue.Empty:
        pass

    _logger.debug('process buffer, len={}'.format(len(buffer)))
    if buffer:
        fst = buffer[0]
        model = fst['model']
        filter_buffer_func = filter_buffer_map[model]
        avg = filter_buffer_func(buffer)
        q_out.put(avg)
    else:
        pass

    _logger.debug('launch new timer thread, %s', thisth.name)
    t = threading.Timer(interval, timed_task, args=(q_in1, q_out, other))
    t.name = thisth.name
    t.start()
