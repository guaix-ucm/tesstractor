#
# Copyright 2018-2019 Universidad Complutense de Madrid
#
# This file is part of tessreader
#
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSE.txt
#


import logging
import time
import re
import datetime

import numpy

from .device import Device, PhotometerConf


MEASURE_RE = re.compile(br"""
                \s* # Skip whitespace
                (?P<cmd>r),
                (?P<magnitude>[\-\s]\d{2}\.\d{2})m,
                (?P<freq>\d{10})Hz,
                (?P<period_counts>\d{10})c,
                (?P<period>\d{7}\.\d{3})s,
                (?P<temp_ambient>[\-\s]\d{3}\.\d)C
                """, re.VERBOSE)

CALIB_RE = re.compile(br"""
                (?P<cmd>c),
                (?P<light_cal>\d{8}\.\d{2})m,
                (?P<dark_period>\d{7}\.\d{3})s,
                (?P<light_cal_temp>[\-\s]\d{3}\.\d)C,
                (?P<off_ref>\d{8}\.\d{2})m,
                (?P<dark_cal_temp>[\-\s]\d{3}\.\d)C
                """, re.VERBOSE)

META_RE = re.compile(br"""
                (?P<cmd>i),
                (?P<protocol_number>\d{8}),
                (?P<model_number>\d{8}),
                (?P<feature_number>\d{8}),
                (?P<serial_number>\d{8})
                """, re.VERBOSE)

_logger = logging.getLogger(__name__)


class SQMConf(PhotometerConf):
    pass


class SQM(Device):
    def __init__(self, name="unknown", model='unknown'):
        super().__init__(name, model)
        # Get Photometer identification codes
        self.protocol_number = 0
        self.model_number = 0
        self.feature_number = 0
        self.serial_number = 0
        self.calibration = 0

        self.ix_readout = ""
        self.rx_readout = ""
        self.cx_readout = ""
        self.cmd_wait = 1

    def static_conf(self):
        conf = SQMConf()
        conf.name = self.name
        conf.model = self.model
        conf.serial_number = self.serial_number
        conf.firmware = self.feature_number
        conf.zero_point = self.calibration
        conf.ix_readout = self.ix_readout
        conf.rx_readout = self.rx_readout
        conf.cx_readout = self.cx_readout
        conf.zero_point = self.calibration
        return conf

    def process_metadata(self, match):
        if match:
            self.ix_readout = match.group()
            self.protocol_number = int(match.group('protocol_number'))
            self.model_number = int(match.group('model_number'))
            self.feature_number = int(match.group('feature_number'))
            self.serial_number = int(match.group('serial_number'))

            return {'cmd': 'i', 'protocol_number': self.protocol_number,
                    'model_number': self.model_number,
                    'feature_number': self.feature_number,
                    'serial_number': self.serial_number}
        else:
            raise ValueError('process_metadata')

    def process_msg(self, match) -> dict:
        """Convert the message from the photometer to unified format"""
        self.rx_readout = match.group()
        result = dict()
        result['name'] = self.name
        result['model'] = 'SQM'
        result['cmd'] = match.group('cmd').decode('utf-8')
        result['magnitude'] = float(match.group('magnitude'))
        #result['freq'] = int(match.group('freq'))
        result['freq_sensor'] = int(match.group('freq'))
        result['period'] = float(match.group('period'))
        result['temp_ambient'] = float(match.group('temp_ambient'))
        result['zero_point'] = self.calibration

        # Add time information
        # Complete the payload with tstamp
        now = datetime.datetime.utcnow()
        result['tstamp'] = now
        return result

    def process_calibration(self, match):
        if match:
            self.cx_readout = match.group()
            self.calibration = float(match.group('light_cal'))
            return {'cmd': 'c', 'calibration': self.calibration}
        else:
            raise ValueError('process_calibration')

    def start_connection(self):
        pass

    def close_connection(self):
        pass

    def reset_device(self):
        """Restart connection"""
        _logger.debug('reset device')
        self.close_connection()
        self.start_connection()

    def read_metadata(self, tries=1):
        """Read the serial number, firmware version."""

        logger = logging.getLogger(__name__)

        cmd = b'ix'
        logger.debug("passing command %s", cmd)
        self.pass_command(cmd)
        time.sleep(self.cmd_wait)

        this_try = 0
        while this_try < tries:
            msg = self.read_msg()
            logger.debug("msg is %s", msg)
            meta_match = META_RE.match(msg)
            if meta_match:
                logger.debug('process metadata')
                pmsg = self.process_metadata(meta_match)
                logger.debug('metadata is %s', pmsg)
                return pmsg
            else:
                logger.warning('malformed metadata, try again')
                this_try += 1
                time.sleep(self.cmd_wait)
                self.reset_device()
                time.sleep(self.cmd_wait)

        logger.error('reading metadata after %d tries', tries)
        raise ValueError

    def read_calibration(self, tries=1):
        """Read the calibration parameters"""

        logger = logging.getLogger(__name__)

        cmd = b'cx'
        logger.debug("passing command %s", cmd)
        self.pass_command(cmd)
        time.sleep(self.cmd_wait)

        this_try = 0
        while this_try < tries:
            msg = self.read_msg()
            logger.debug("msg is %s", msg)
            match = CALIB_RE.match(msg)
            if match:
                logger.debug('process calibration')
                pmsg = self.process_calibration(match)
                logger.debug('calibration is %s', pmsg)
                return pmsg
            else:
                logger.warning('malformed calibration, try again')
                this_try += 1
                time.sleep(self.cmd_wait)
                self.reset_device()
                time.sleep(self.cmd_wait)

        logger.error('reading calibration after %d tries', tries)
        raise ValueError

    def read_data(self, tries=1):
        """Read the calibration parameters"""

        logger = logging.getLogger(__name__)

        cmd = b'rx'
        logger.debug("passing command %s", cmd)
        self.pass_command(cmd)
        time.sleep(self.cmd_wait)

        this_try = 0
        while this_try < tries:
            msg = self.read_msg()
            logger.debug("msg is %s", msg)
            match = MEASURE_RE.match(msg)
            if match:
                pmsg = self.process_msg(match)
                logger.debug('data is %s', pmsg)

                if pmsg['magnitude'] < 0:
                    logger.warning('negative measured magnitude, try again')
                    this_try += 1
                    time.sleep(self.cmd_wait)
                    continue

                return pmsg
            else:
                logger.warning('malformed data, try again')
                logger.debug('data is %s', msg)
                this_try += 1
                time.sleep(self.cmd_wait)
                self.reset_device()
                time.sleep(self.cmd_wait)

        logger.error('reading data after %d tries', tries)
        return None

    def pass_command(self, cmd):
        pass

    def read_msg(self):
        return b''


class SQMLU(SQM):
    def __init__(self, conn, name="", sleep_time=1, tries=10):
        super().__init__(name=name, model='SQM-LU')
        self.serial = conn
        # Clearing buffer
        self.read_msg()

    def start_connection(self):
        """Start photometer connection"""
        _logger.debug('start connection')
        time.sleep(self.cmd_wait)
        self.read_metadata(tries=10)
        time.sleep(self.cmd_wait)
        self.read_calibration(tries=10)
        time.sleep(self.cmd_wait)
        self.read_data(tries=10)

    def close_connection(self):
        """End photometer connection"""
        # Check until there is no answer from device
        _logger.debug('close connection')
        answer = True
        while answer:
            answer = self.read_msg()

        self.serial.close()

    def read_msg(self):
        """Read the data"""
        msg = self.serial.readline()
        return msg

    def pass_command(self, cmd):
        self.serial.write(cmd)


class SQMTest(SQM):
    def __init__(self):
        super().__init__(name='sqmtest', model='SQM-TEST')
        self.ix = b'i,00000004,00000003,00000023,00002142\r\n'
        self.cx = b'c,00000019.84m,0000151.517s, 022.2C,00000008.71m, 023.2C\r\n'
        self.rx = b'r, 19.29m,0000000002Hz,0000277871c,0000000.603s, 029.9C\r\n'

    def start_connection(self):
        """Start photometer connection"""
        self.read_metadata()
        self.read_calibration()
        self.read_data()

    def read_metadata(self, tries=1):
        """Read the serial number, firmware version."""
        msg = self.ix
        match = META_RE.match(msg)
        return self.process_metadata(match)

    def read_calibration(self, tries=1):
        """Read the calibration parameters"""
        msg = self.cx
        match = CALIB_RE.match(msg)
        return self.process_calibration(match)

    def read_data(self, tries=1):
        msg = self.rx
        match = MEASURE_RE.match(msg)
        return self.process_msg(match)
