# PySQM reading program
# ____________________________
#
# Copyright (c) Miguel Nievas <miguelnievas[at]ucm[dot]es>
#
# This file is part of PySQM.
#
# PySQM is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# PySQM is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PySQM.  If not, see <http://www.gnu.org/licenses/>.
# ____________________________

from __future__ import print_function

import logging
import struct
import sys
import time
import datetime
import socket
import serial

import numpy as np

import pysqm.common



# Default, to ignore the length of the read string.
_cal_len_ = None
_meta_len_ = None
_data_len_ = None


def filtered_mean(array, sigma=3):
    # Our data probably contains outliers, filter them
    # Notes:
    #   Median is more robust than mean
    #    Std increases if the outliers are far away from real values.
    #    We need to limit the amount of discrepancy we want in the data (20%?).

    # We will use data masking and some operations with arrays. Convert to numpy.
    array = np.array(array)

    # Get the median and std.
    data_median = np.median(array)
    data_std = np.std(array)

    # Max discrepancy we allow.
    fixed_max_dev = 0.2 * data_median
    clip_deviation = np.min([fixed_max_dev, data_std * sigma])

    # Create the filter (10% flux + variable factor)
    filter_values_ok = np.abs(array - data_median) <= clip_deviation
    filtered_values = array[filter_values_ok]

    # Return the mean of filtered data or the median.
    if np.size(filtered_values) == 0:
        logger = logging.getLogger(__name__)
        logger.warn('High dispersion found on last measures')
        filtered_mean = data_median
    else:
        filtered_mean = np.mean(filtered_values)

    return (filtered_mean)


class Device(object):
    def __init__(self):
        self.DataCache = ""

    def data_cache(self, formatted_data, store, number_measures=1, niter=0):
        '''
        Append data to DataCache str.
        If len(data)>number_measures, write to file
        and flush the cache
        '''

        self.DataCache = self.DataCache + formatted_data

        if len(self.DataCache.split("\n")) >= number_measures + 1:
            logger = logging.getLogger(__name__)
            store.save_data(self.DataCache)
            self.DataCache = ""
            logger.info('%d\t%s', niter, formatted_data[:-1])

    def flush_cache(self, store):
        ''' Flush the data cache '''
        store.save_data(self.DataCache)
        self.DataCache = ""


class SQM(Device):
    def __init__(self):
        super(SQM, self).__init__()
        # Get Photometer identification codes
        self.protocol_number = 0
        self.model_number = 0
        self.feature_number = 0
        self.serial_number = 0

        self.ix_readout = ""
        self.rx_readout = ""
        self.cx_readout = ""


    def pass_command(self, cmd):
        raise NotImplemented

    def read_photometer(self, dtz, Nmeasures=1, PauseMeasures=2):
        # Initialize values
        temp_sensor = []
        flux_sensor = []
        freq_sensor = []
        ticks_uC = []
        Nremaining = Nmeasures

        # Promediate N measures to remove jitter
        # timeutc_initial = obs.read_datetime()
        timeutc_initial = 0
        while (Nremaining > 0):
            InitialDateTime = datetime.datetime.now()

            # Get the raw data from the photometer and process it.
            raw_data = self.read_data(tries=10)
            temp_sensor_i, freq_sensor_i, ticks_uC_i, sky_brightness_i = \
                self.data_process(raw_data)

            temp_sensor += [temp_sensor_i]
            freq_sensor += [freq_sensor_i]
            ticks_uC += [ticks_uC_i]
            flux_sensor += [10 ** (-0.4 * sky_brightness_i)]
            Nremaining -= 1
            DeltaSeconds = (datetime.datetime.now() - InitialDateTime).total_seconds()

            # Just to show on screen that the program is alive and running
            # sys.stdout.write('.')
            # sys.stdout.flush()

            if Nremaining > 0:
                time.sleep(max(1, PauseMeasures - DeltaSeconds))

        timeutc_final = 0 # obs.read_datetime()
        timeutc_delta = timeutc_final - timeutc_initial

        timeutc_mean = timeutc_initial + \
                       datetime.timedelta(seconds=int(timeutc_delta.seconds / 2. + 0.5))
        timelocal_mean = 0 # obs.local_datetime(timeutc_mean, dtz)

        # Calculate the mean of the data.
        temp_sensor = filtered_mean(temp_sensor)
        freq_sensor = filtered_mean(freq_sensor)
        flux_sensor = filtered_mean(flux_sensor)
        ticks_uC = filtered_mean(ticks_uC)
        sky_brightness = -2.5 * np.log10(flux_sensor)

        # Correct from offset (if cover is installed on the photometer)
        # sky_brightness = sky_brightness+config._offset_calibration

        return (
            timeutc_mean, timelocal_mean,
            temp_sensor, freq_sensor,
            ticks_uC, sky_brightness)

    def metadata_process(self, msg, sep=','):
        # Separate the output array in items
        msg = pysqm.common.format_value(msg)
        msg_array = msg.split(sep)

        # Get Photometer identification codes
        self.protocol_number = int(pysqm.common.format_value(msg_array[1]))
        self.model_number = int(pysqm.common.format_value(msg_array[2]))
        self.feature_number = int(pysqm.common.format_value(msg_array[3]))
        self.serial_number = int(pysqm.common.format_value(msg_array[4]))

    def data_process(self, msg, sep=','):
        # Separate the output array in items
        msg = pysqm.common.format_value(msg)
        msg_array = msg.split(sep)

        # Output definition characters
        mag_char = 'm'
        freq_char = 'Hz'
        perc_char = 'c'
        pers_char = 's'
        temp_char = 'C'

        # Get the measures
        sky_brightness = float(pysqm.common.format_value(msg_array[1], mag_char))
        freq_sensor = float(pysqm.common.format_value(msg_array[2], freq_char))
        ticks_uC = float(pysqm.common.format_value(msg_array[3], perc_char))
        period_sensor = float(pysqm.common.format_value(msg_array[4], pers_char))
        temp_sensor = float(pysqm.common.format_value(msg_array[5], temp_char))

        # For low frequencies, use the period instead
        if freq_sensor < 30 and period_sensor > 0:
            freq_sensor = 1. / period_sensor

        return (temp_sensor, freq_sensor, ticks_uC, sky_brightness)

    def start_connection(self):
        """Start photometer connection"""
        raise NotImplemented

    def close_connection(self):
        """End photometer connection"""
        raise NotImplemented

    def reset_device(self):
        """Restart connection"""
        self.close_connection()
        self.start_connection()

    def read_buffer(self):
        raise NotImplemented

    def read_metadata(self, tries=1, wait=1):
        """Read the serial number, firmware version."""

        logger = logging.getLogger(__name__)

        self.pass_command(b'ix')
        time.sleep(wait)

        read_err = False
        msg = self.read_buffer()
        print(msg, type(msg))
        # Check metadata
        if (len(msg) == _meta_len_ or _meta_len_ is None) and b'i,' in msg:
            self.metadata_process(msg.decode('ascii'))
        else:
            tries -= 1
            read_err = True

        if read_err and tries > 0:
            time.sleep(1)
            self.reset_device()
            time.sleep(1)
            msg = self.read_metadata(tries)
            if (msg != -1): read_err = False

        # Check that msg contains data
        if read_err:
            logger.error('Reading the photometer!: %s', msg[:-1])
            return -1
        else:
            logger.info('Sensor info: %s', msg[:-1])
            return msg

    def read_calibration(self, tries=1):
        ''' Read the calibration parameters '''
        self.pass_command(b'cx')
        time.sleep(1)
        logger = logging.getLogger(__name__)
        read_err = False
        msg = self.read_buffer()

        # Check caldata
        if (len(msg) == _cal_len_ or _cal_len_ is None) and b"c," in msg:
            pass
        else:
            tries -= 1
            read_err = True

        if read_err and tries > 0:
            time.sleep(1)
            self.reset_device()
            time.sleep(1)
            msg = self.read_calibration(tries)
            if (msg != -1):
                read_err = False

        # Check that msg contains data
        if read_err == True:
            logger.error('Reading the photometer!: %s', msg[:-1])
            return -1
        else:
            logger.info('Calibration info: %s', msg[:-1])
            return (msg)

    def read_data(self, tries=1):
        """Read the SQM and format the Temperature, Frequency and NSB measures"""
        self.pass_command(b'rx')
        time.sleep(1)
        logger = logging.getLogger(__name__)
        read_err = False
        msg = self.read_buffer()

        # Check data
        if (len(msg) == _data_len_ or _data_len_ is None) and (b'r,' in msg):
            # Sanity check
            self.data_process(msg.decode('ascii'))
        else:
            tries -= 1
            read_err = True

        if read_err and tries > 0:
            time.sleep(1)
            self.reset_device()
            time.sleep(1)
            msg = self.read_data(tries)
            if (msg != -1):
                read_err = False

        # Check that msg contains data
        if read_err:
            logger.error('Reading the photometer!: %s', msg[:-1])
            return -1
        else:
            logger.debug('Data msg: %s', msg[:-1])

            return msg


class SQMLE(SQM):
    def __init__(self, addr, port=10001):
        """Search the photometer in the network and read its metadata"""

        super(SQMLE, self).__init__()
        self.port = port
        self.addr = addr
        self.start_connection()
        logger = logging.getLogger(__name__)
        # Clearing buffer
        logger.info('Clearing buffer')
        buffer_data = self.read_buffer()
        logger.info(buffer_data),
        logger.info('done')
        logger.info('Reading test data (ix,cx,rx)...')
        time.sleep(1)
        self.ix_readout = self.read_metadata(tries=10)
        time.sleep(1)
        self.cx_readout = self.read_calibration(tries=10)
        time.sleep(1)
        self.rx_readout = self.read_data(tries=10)

    @staticmethod
    def search():
        """Search SQM LE in the LAN. Return its adress"""
        logger = logging.getLogger(__name__)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setblocking(False)

        if hasattr(socket, 'SO_BROADCAST'):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        s.sendto("000000f6".decode("hex"), ("255.255.255.255", 30718))
        starttime = time.time()

        addr = [None, None]
        while True:
            try:
                (buf, addr) = s.recvfrom(30)
                if buf[3].encode("hex") == "f7":
                    logger.info("Received from %s: MAC: %s", addr, buf[24:30].encode("hex"))
            except:
                # Timeout in seconds. Allow all devices time to respond
                if time.time() - starttime > 3:
                    break

        if addr[0] is None:
            logger.error('Device not found!')
            raise
        else:
            return addr[0]

    def pass_command(self, cmd):
        self.s.send(cmd)

    def start_connection(self):
        """Start photometer connection."""
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.settimeout(20)
        self.s.connect((self.addr, int(self.port)))
        # self.s.settimeout(1)

    def close_connection(self):
        """End photometer connection"""
        self.s.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_LINGER,
            struct.pack('ii', 1, 0))

        # Check until there is no answer from device
        request = ""
        r = True
        while r:
            r = self.read_buffer()
            request += str(r)
        self.s.close()

    def read_buffer(self):
        """Read the data"""
        msg = None
        try:
            msg = self.s.recv(256)
        except:
            pass
        return msg


class SQMLU(SQM):
    def __init__(self, addr, bauds=115200):
        """Search the photometer and read its metadata"""

        super(SQMLU, self).__init__()

        self.bauds = bauds
        self.addr = addr
        self.serial = None
        self.ix_readout = None
        self.cx_readout = None
        self.rx_readout = None

    def open(self, wait=1):
        self.serial = self.init_connection(self.addr, self.bauds)
        # Clearing buffer
        print('Clearing buffer ... |')
        buffer_data = self.read_buffer()
        print("%s" % buffer_data)
        print('|done')
        print('Reading test data (ix,cx,rx)...')
        time.sleep(wait)
        self.ix_readout = self.read_metadata(tries=10)
        print(self.ix_readout)
        time.sleep(wait)
        self.cx_readout = self.read_calibration(tries=10)
        print(self.cx_readout)
        time.sleep(wait)
        self.rx_readout = self.read_data(tries=10)
        print(self.rx_readout)

    @staticmethod
    def search(bauds=115200):
        """Serial photometer search."""

        logger = logging.getLogger(__name__)
        # Name of the port depends on the platform.
        ports_unix = ['/dev/ttyUSB%d' % num for num in range(100)]
        ports_win = ['COM%d' % num for num in range(100)]

        os_in_use = sys.platform

        ports = []
        if os_in_use == 'linux2':
            logger.info('Detected Linux platform')
            ports = ports_unix
        elif os_in_use == 'win32':
            logger.info('Detected Windows platform')
            ports = ports_win

        used_port = None
        for port in ports:
            conn_test = serial.Serial(port, bauds, timeout=1)
            conn_test.write('ix')
            if conn_test.readline()[0] == 'i':
                used_port = port
                break

        if used_port is None:
            logger.error('Device not found!')
            raise
        else:
            return used_port

    @staticmethod
    def init_connection(addr, bauds):
        """Start serial photometer connection"""
        return serial.Serial(addr, bauds, timeout=2)

    def start_connection(self):
        """Start photometer connection"""

        self.serial = self.init_connection(self.addr, self.bauds)

    def close_connection(self):
        ''' End photometer connection '''
        # Check until there is no answer from device
        request = ""
        r = True
        while r:
            r = self.read_buffer()
            request += str(r)

        self.serial.close()

    def read_buffer(self):
        """Read the data"""
        msg = None
        try:
            msg = self.serial.readline()
        except:
            pass
        return msg

    def pass_command(self, cmd):
        res = self.serial.write(cmd)
        print('pass comand', cmd, 'bytes written', res)

if __name__ == '__main__':

    a = SQMLU('/dev/ttyUSB0')
    a.open()