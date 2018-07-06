#
# Copyright 2018 Universidad Complutense de Madrid
#
# This file is part of pysqm-lite
#
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSE.txt
#


import logging


_logger = logging.getLogger(__name__)


def consumer_write_file(q, other):
    _logger.info('starting file writer consumer')

    while True:
        payload = q.get()
        if payload:
            _logger.debug('got (w) payload %s', payload)
            res = write_to_file(payload)
            _logger.debug('server says %s', res)
            q.task_done()
        else:
            _logger.info('end file writer consumer thread')
            other.client.loop_stop()
            break


def write_to_file(payload):
    _logger.debug('write payload %s to file', payload)
    with open('dum.txt', 'a') as fd:
        fd.write('%{}'.format(payload))
    return 0