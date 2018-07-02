#
# Copyright 2018 Universidad Complutense de Madrid
#
# This file is part of pysqm-lite
#
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSE.txt
#


import logging
import time
import re

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
                """, re.VERBOSE)

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
                """, re.VERBOSE)

META_RE = re.compile(br"""
                \s* # Skip whitespace
                (?P<cmd>i) # Command
                ,\s*
                (?P<protocol_number>\d*)
                ,\s*(?P<model_number>\d*),\s*
                (?P<feature_number>\d*),\s*(?P<serial_number>\d*)
                """, re.VERBOSE)


class SQM(object):
    def __init__(self):
        super(SQM, self).__init__()
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

    def process_metadata(self, match):
        self.protocol_number = int(match.group('protocol_number'))
        self.model_number = int(match.group('model_number'))
        self.feature_number = int(match.group('feature_number'))
        self.serial_number = int(match.group('serial_number'))

        return {'cmd': 'i', 'protocol_number': self.protocol_number,
                'model_number': self.model_number,
                'feature_number': self.feature_number,
                'serial_number': self.serial_number}

    def process_data(self, match):
        if match:
            result = {}
            # result['mode'] = 'data'
            result['cmd'] = match.group('cmd').decode('utf-8')
            result['sky_brightness'] = float(match.group('sky_brightness'))
            result['freq_sensor'] = int(match.group('freq_sensor'))
            result['period_sensor'] = float(match.group('period_sensor'))
            result['temp_sensor'] = float(match.group('temp_sensor'))
            return result
        else:
            raise ValueError

    def process_calibration(self, match):
        if match:
            self.calibration = float(match.group('light_cal'))
            return {'cmd': 'c', 'calibration': self.calibration}
        else:
            raise ValueError

    def start_connection(self):
        pass

    def close_connection(self):
        pass

    def reset_device(self):
        """Restart connection"""
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
            match = MEASURE_RE.match(msg)
            if match:
                logger.debug('process data')
                pmsg = self.process_data(match)
                logger.debug('data is %s', pmsg)
                return pmsg
            else:
                logger.warning('malformed data, try again')
                this_try += 1
                time.sleep(self.cmd_wait)
                self.reset_device()
                time.sleep(self.cmd_wait)

        logger.error('reading data after %d tries', tries)
        raise ValueError

    def pass_command(self, cmd):
        pass

    def read_msg(self):
        return b''


class SQMLU(SQM):
    def __init__(self, conn, name="", sleep_time=1, tries=10):
        # def __init__(self, addr, bauds=115200):
        """Search the photometer and read its metadata"""

        super(SQMLU, self).__init__()
        self.serial = conn
        self.name = name
        # Clearing buffer
        self.read_msg()

    def start_connection(self):
        """Start photometer connection"""
        time.sleep(self.cmd_wait)
        self.ix_readout = self.read_metadata(tries=10)
        time.sleep(self.cmd_wait)
        self.cx_readout = self.read_calibration(tries=10)
        time.sleep(self.cmd_wait)
        self.rx_readout = self.read_data(tries=10)

    def close_connection(self):
        """End photometer connection"""
        # Check until there is no answer from device
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
        super().__init__()
        self.ix = b'i,00000004,00000003,00000023,00002142\r\n'
        self.cx = b'c,00000019.84m,0000151.517s, 022.2C,00000008.71m, 023.2C\r\n'
        self.rx = b'r, 19.29m,0000000002Hz,0000277871c,0000000.603s, 029.9C\r\n'

        self.protocol_number = 0
        self.model_number = 0
        self.feature_number = 0
        self.serial_number = 0
        self.calibration = 0
        self.name = 'sqmtest'

    def start_connection(self):
        """Start photometer connection"""
        self.ix_readout = self.read_metadata()
        self.cx_readout = self.read_calibration()
        self.rx_readout = self.read_data()

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
        return self.process_data(match)
