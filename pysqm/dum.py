
from __future__ import print_function

import logging
import time
import serial
import re

import numpy as np

# Default, to ignore the length of the read string.
CAL_LEN = None
META_LEN = None
DATA_LEN = None

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

        self.pr = re.compile(br"""
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
                """
               , re.VERBOSE)

        self.calib = re.compile(br"""
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
                """
               , re.VERBOSE)

        self.meta = re.compile(br"""
                \s* # Skip whitespace
                (?P<cmd>i) # Command
                ,\s*
                (?P<protocol_number>\d*)
                ,\s*(?P<model_number>\d*),\s*
                (?P<feature_number>\d*),\s*(?P<serial_number>\d*)
                """
               , re.VERBOSE)

    def read_photometer(self, dtz, nmeasures=1, pause_measures=2):
        # Initialize values

        logger = logging.getLogger(__name__)
        temp_sensor = []
        flux_sensor = []
        freq_sensor = []
        ticks_uC = []
        nremaining = nmeasures

        # Promediate N measures to remove jitter
        timeutc_initial = datetime.datetime.utcnow()
        while nremaining > 0:
            initial_datetime = datetime.datetime.now()

            # Get the raw data from the photometer and process it.
            raw_data = self.read_data(tries=10)
            logger.debug("raw data |%s|", raw_data[:-1])
            temp_sensor_i, freq_sensor_i, ticks_uC_i, sky_brightness_i = \
                self.data_process(raw_data)

            temp_sensor.append(temp_sensor_i)
            freq_sensor.append(freq_sensor_i)
            ticks_uC.append(ticks_uC_i)

            flux_sensor.append(10 ** (-0.4 * sky_brightness_i))

            nremaining -= 1
            deltaseconds = (datetime.datetime.now() - initial_datetime).total_seconds()

            if nremaining > 0:
                time.sleep(max(1, pause_measures - deltaseconds))

        timeutc_final = datetime.datetime.utcnow()
        timeutc_delta = timeutc_final - timeutc_initial

        timeutc_mean = timeutc_initial + datetime.timedelta(seconds=int(timeutc_delta.seconds / 2. + 0.5))
        timelocal_mean = obs.local_datetime(timeutc_mean, dtz)

        # Calculate the mean of the data.
        temp_sensor = filtered_mean(temp_sensor)
        freq_sensor = filtered_mean(freq_sensor)
        flux_sensor = filtered_mean(flux_sensor)
        ticks_uC = filtered_mean(ticks_uC)
        sky_brightness = -2.5 * np.log10(flux_sensor)

        # Correct from offset (if cover is installed on the photometer)
        # sky_brightness = sky_brightness+config._offset_calibration

        return timeutc_mean, timelocal_mean, temp_sensor, freq_sensor, ticks_uC, sky_brightness

    def metadata_process(self, match):
        self.protocol_number = int(match.group('protocol_number'))
        self.model_number = int(match.group('model_number'))
        self.feature_number = int(match.group('feature_number'))
        self.serial_number = int(match.group('serial_number'))

    def data_process(self, msg, sep=','):

        # Separate the output array in items
        msg_array = msg.split(sep)

        # Get the measures
        sky_brightness = msg_array[1]
        freq_sensor = msg_array[2]
        ticks_uC = msg_array[3]
        period_sensor = msg_array[4]
        temp_sensor = msg_array[5]

        # For low frequencies, use the period instead
        if freq_sensor < 30 and period_sensor > 0:
            freq_sensor = 1. / period_sensor

        return temp_sensor, freq_sensor, ticks_uC, sky_brightness

    def reset_device(self):
        """Restart connection"""
        self.close_connection()
        self.start_connection()

    def read_metadata(self, tries=1):
        """Read the serial number, firmware version."""

        logger = logging.getLogger(__name__)

        self.pass_command(b'ix')
        time.sleep(1)

        print('metadata')
        read_err = False
        msg = self.read_msg()
        print(msg)
        m = self.meta.match(msg)
        if m:
            self.metadata_process(m)
        else:
            tries -= 1
            read_err = True

        if read_err and tries > 0:
            time.sleep(1)
            self.reset_device()
            time.sleep(1)
            msg = self.read_metadata(tries)
            if (msg != -1): 
                read_err = False

        # Check that msg contains data
        if read_err:
            logger.error('Reading the photometer!: %s', msg[:-1])
            return -1
        else:
            logger.info('Sensor info: %s', msg[:-1])
            return msg

    def read_calibration(self, tries=1):
        """Read the calibration parameters"""

        logger = logging.getLogger(__name__)
        read_err = False

        self.pass_command(b'cx')
        time.sleep(1)

        msg = self.read_msg()
        m = self.calib.match(msg)
        if m:
            self.calibration = float(m.group('light_cal'))
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

    def pass_command(self, cmd):
        pass

    def read_msg(self):
        return b''

    def read_data(self, tries=1):
        """Read the SQM and format the Temperature, Frequency and NSB measures"""

        logger = logging.getLogger(__name__)

        self.pass_command(b'rx')
        time.sleep(1)

        msg = self.read_msg()

        m = self.pr.match(msg)
        if m:
            result = {}
            result['cmd'] = m.group('cmd').decode('utf-8')
            result['sky_brightness'] =  float(m.group('sky_brightness'))
            result['freq_sensor'] = int(m.group('freq_sensor'))
            result['period_sensor'] = float(m.group('period_sensor'))
            result['temp_sensor'] = float(m.group('temp_sensor'))
            return result
        else:
            if tries > 0:
                time.sleep(1)
                logger.warning('Reset device after read error')
                self.reset_device()
                time.sleep(1)
                return self.read_data(tries - 1)
            else:
                return None


class SQMLU(SQM):
    def __init__(self, addr, bauds=115200):
        """Search the photometer and read its metadata"""

        super(SQMLU, self).__init__()

        self.bauds = bauds
        self.addr = addr
        self.serial = self.init_connection(self.addr, self.bauds)

        # Clearing buffer
        self.read_msg()

        time.sleep(1)
        self.ix_readout = self.read_metadata(tries=10)
        time.sleep(1)
        self.cx_readout = self.read_calibration(tries=10)
        time.sleep(1)
        self.rx_readout = self.read_data(tries=10)

    @staticmethod
    def init_connection(addr, bauds):
        """Start serial photometer connection"""
        return serial.Serial(addr, bauds, timeout=2)

    def start_connection(self):
        """Start photometer connection"""
        self.serial = self.init_connection(self.addr, self.bauds)

    def close_connection(self):
        """End photometer connection"""
        # Check until there is no answer from device
        request = ""
        r = True
        while r:
            r = self.read_msg()
            request += str(r)

        self.serial.close()

    def read_msg(self):
        """Read the data"""
        msg = self.serial.readline()
        return msg

    def pass_command(self, cmd):
        self.serial.write(cmd)


if __name__ == '__main__':
    import paho.mqtt.client as mqtt
    import json
    import pytz
    import datetime
    from configS import SQM_CONFIG

    print('init')
    sqm = SQMLU('/dev/ttyUSB0')
    print(sqm.serial_number)
    print('done')

    tz = pytz.utc

    publish_topic = 'STARS4ALL/{}/reading'.format(SQM_CONFIG['channel'])
    mac = sqm.serial_number

    client = mqtt.Client()
    client.username_pw_set(SQM_CONFIG['username'], password=SQM_CONFIG['password'])
    client.connect(SQM_CONFIG['hostname'], 1883, 60)
    client.loop_start()

    # register on power up
    payload = dict(name=SQM_CONFIG['name'], mac=mac, calib=sqm.calibration, rev=1, chan=SQM_CONFIG['channel'])
    spayload = json.dumps(payload)
    response = client.publish(SQM_CONFIG['register_topic'], spayload)
    print('register, payload', spayload)
    print('register, response', response)

    seq = 1
    timeout = 60
    payload = dict(seq=0, name=SQM_CONFIG['name'], freq=0.0, mag=0.0, tamb=0.0, tsky=0.0, rev=1)
    half_s = datetime.timedelta(seconds=0.5)
    while True:
        # now = datetime.datetime.now(tz=pytz.utc)
        now = datetime.datetime.utcnow()
        msg = sqm.read_data()

        print('message is:', msg)
        now.isoformat()
        payload['seq'] = seq
        # 'freq_sensor': 15370, 'period_sensor': 0.0,
        payload['freq'] = msg['period_sensor']
        payload['mag'] = msg['sky_brightness']
        payload['tamb'] = msg['temp_sensor']
        # payload['tstamp'] = now.isoformat()
        # round to nearest second
        payload['tstamp'] = (now + half_s).strftime("%Y-%m-%dT%H:%M:%S")
        spayload = json.dumps(payload)

        print('payload is:', spayload)
        response = client.publish(publish_topic, spayload, qos=0)
        print('publish, response', response)

        seq += 1
        time.sleep(timeout)

    # client.loop_stop()
