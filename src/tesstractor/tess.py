#
# Copyright 2018-2024 Universidad Complutense de Madrid
#
# This file is part of tesstractor
#
# SPDX-License-Identifier: GPL-3.0-or-later
# License-Filename: LICENSE.txt
#


import logging
import time
import re
import math
import datetime
import json
import typing
import warnings

from .device import Device, PhotometerConf

MEASURE_RE = re.compile(
    rb"""
    ^(<f(?P<freq_pref>[mH])((?P<freq_u>(?<=m)-.{5})|(?P<freq_o>(?<=H)-.{5})|(?P<freq>\ \d{5}))>
    (<tA\ (?P<temp_ambient>[+-]\d{4})>)? # white space is ignored, so "\ "
    (<tO\ (?P<temp_sky>[+-]\d{4})>)?
    (<aX\ (?P<acc_x>[+-]\d{4})>)?
    (<aY\ (?P<acc_y>[+-]\d{4})>)?
    (<aZ\ (?P<acc_z>[+-]\d{4})>)?
    (<mX\ (?P<mag_x>[+-]\d{4})>)?
    (<mY\ (?P<mag_y>[+-]\d{4})>)?
    (<mZ\ (?P<mag_z>[+-]\d{4})>)?
    (?P<counter>\d+)?)?
    \r\n
    """,
    re.VERBOSE,
)


_logger = logging.getLogger(__name__)


class TESSConf(PhotometerConf):
    pass


class Tess(Device):
    """Generic TESS device"""

    def __init__(self, name="unknown", model="unknown"):
        super().__init__(name, model)
        # Get Photometer identification codes
        self.protocol_number = 0
        self.model_number = 0
        self.feature_number = 0

        self.mac = "01:23:45:67:89:AB"
        self.cmd_wait = 0
        self.counts = 1

    def static_conf(self):
        conf = TESSConf()
        conf.name = self.serial_number
        conf.model = self.model
        conf.serial_number = self.serial_number
        conf.firmware = self.feature_number
        conf.zero_point = self.calibration
        conf.mac_address = self.mac
        return conf

    def register_id(self):
        """ID used for registration"""
        return self.mac

    def process_metadata(self, match):
        if match:
            return {
                "cmd": "i",
                "protocol_number": self.protocol_number,
                "model_number": self.model_number,
                "feature_number": self.feature_number,
                "serial_number": self.serial_number,
            }
        else:
            raise ValueError("process_metadata")

    def process_msg(self, match):
        re_m = match.groupdict()
        # temps
        result = dict()
        result["cmd"] = "r"
        result["freq"] = 0.0
        result["magnitude"] = 99.0
        result["name"] = self.name
        result["model"] = "TESS"
        result["freq_sensor"] = 0.0
        result["zero_point"] = self.calibration
        result["valid"] = False
        result["tstamp"] = datetime.datetime.utcnow()

        if re_m["freq_pref"] is None:
            return result
        else:
            if re_m["freq_o"] is not None:
                # overflow
                return result
            if re_m["freq_u"] is not None:
                # underflow
                return result

            if re_m["freq_pref"] == b"m":
                result["freq"] = int(re_m["freq"]) / 1000.0
            elif re_m["freq_pref"] == b"H":
                result["freq"] = int(re_m["freq"]) / 1.0
            else:
                raise ValueError("freq_pref")
            result["freq_sensor"] = result["freq"]
            result["magnitude"] = self.calibration - 2.5 * math.log10(result["freq"])
        acc_keys = ["temp_ambient", "temp_sky"]
        for key in acc_keys:
            if re_m[key] is not None:
                result[key] = int(re_m[key]) / 100.0

        acc_keys = ["acc_x", "acc_y", "acc_z"]

        for key in acc_keys:
            if re_m[key] is not None:
                result[key] = int(re_m[key])

        acc_keys = ["mag_x", "mag_y", "mag_z"]

        for key in acc_keys:
            if re_m[key] is not None:
                result[key] = int(re_m[key])

        result["valid"] = True
        return result

    def check_capabilities(self, match):

        key_f = "freq_pref"
        # flux_keys = ['freq_pref', 'freq_o', 'freq_u', 'freq']
        temp_keys = ["temp_ambient", "temp_sky"]
        acc_keys = ["acc_x", "acc_y", "acc_z"]
        mag_keys = ["mag_x", "mag_y", "mag_z"]

        capabilities = dict(
            has_flux=False,
            has_acc=False,
            has_mag=False,
        )

        for key in temp_keys:
            capabilities["has_{}".format(key)] = False

        re_m = match.groupdict()

        if re_m.get(key_f, None) is not None:
            capabilities["has_flux"] = True

        for key in temp_keys:
            if re_m.get(key, None) is not None:
                capabilities["has_{}".format(key)] = True
        capabilities["has_acc"] = all(re_m.get(k, None) is not None for k in acc_keys)
        capabilities["has_mag"] = all(re_m.get(k, None) is not None for k in mag_keys)

        return capabilities

    def process_calibration(self, match):
        if match:
            return {"cmd": "c", "calibration": self.calibration}
        else:
            raise ValueError("process_calibration")

    def start_connection(self):
        pass

    def close_connection(self):
        pass

    def reset_device(self):
        """Discard pending input"""
        _logger.debug("reset device")

    def read_metadata(self, tries=1):
        """Read the serial number, firmware version."""

        logger = logging.getLogger(__name__)
        # Read data to check capabilities

        this_try = 0
        while this_try < tries:
            msg = self.read_msg()
            logger.debug("metadata msg is %s", msg)
            match = MEASURE_RE.match(msg)
            if match:
                # check capabilities
                logger.debug("metadata is %s", msg)
                self.check_capabilities(match)
                return msg
            else:
                logger.warning("malformed data, ignoring %s", msg)
                logger.debug("data is %s", msg)
                this_try += 1

        msg = "reading data after {} tries".format(tries)
        logger.error(msg)
        raise ValueError(msg)

    def read_calibration(self, tries=1):
        """Read the calibration parameters"""

        pmsg = {}
        return pmsg

    def read_data(self, tries=1):
        """Read measurements"""

        logger = logging.getLogger(__name__)

        this_try = 0
        while this_try < tries:
            msg = self.read_msg()
            logger.debug("msg is %s", msg)
            match = MEASURE_RE.match(msg)
            if match:
                logger.debug("process data")
                pmsg = self.process_msg(match)
                logger.debug("data is %s", pmsg)
                return pmsg
            else:
                logger.warning("malformed data, ignoring %s", msg)
                this_try += 1
                time.sleep(self.cmd_wait)
                self.reset_device()

        logger.error("reading data after %d tries", tries)
        return None

    def pass_command(self, cmd):
        pass

    def read_msg(self):
        return b""


class TessR(Tess):
    def __init__(self, conn, name="tess", sleep_time=1, tries=10):
        super().__init__(name=name, model="TESS-R")
        self.serial = conn

    def start_connection(self):
        """Start photometer connection"""
        _logger.debug("start connection")
        if not self.serial.is_open:
            self.serial.open()
        self.serial.reset_input_buffer()

        self.read_metadata(tries=10)
        self.read_calibration(tries=10)
        self.read_data(tries=10)

    def reset_device(self):
        """Discard pending input, reopening the port if needed"""
        _logger.debug("reset device")
        if not self.serial.is_open:
            self.serial.open()
        self.serial.reset_input_buffer()

    def close_connection(self):
        """End photometer connection"""
        # Check until there is no answer from device
        _logger.debug("close connection")
        self.serial.close()

    def read_msg(self):
        """Read the data"""
        msg = self.serial.readline()
        return msg

    def pass_command(self, cmd):
        self.serial.write(cmd)


class TessV2(Tess):
    """TESS serial V2

    The output format of this photometer mixes text with json with this fields:

    {
    "udp":83471,  output number , ignoring
    "rev":2,
    "name":"stars605",
    "freq":13.38,
    "mag":17.52,
    "tamb":30.39,
    "tsky":29.23,
    "wdBm":-50,  wifi power, ignoring
    "ain":448, analog input, ignoring
    "ZP":20.34  zero_point
    }


    """

    def __init__(self, conn, name="tess", sleep_time=1, tries=10):
        super().__init__(name=name, model="TESSv2")
        self.serial = conn

    def start_connection(self):
        """Start photometer connection"""
        _logger.debug("start connection")
        if not self.serial.is_open:
            self.serial.open()
        self.serial.reset_input_buffer()

    def close_connection(self):
        """End photometer connection"""
        _logger.debug("close connection")
        self.serial.close()

    def read_msg(self):
        """Read messages from the photometer"""
        msg = self.serial.readline()
        return msg

    def pass_command(self, cmd):
        # We can't pass commands
        pass

    def read_metadata(self, tries=1):
        # We can't ask the photometer its values
        pass

    def read_data(self, tries=1):
        """Read measurements"""

        # This TESS mixes messages with actual data
        # and sometimes expends a lot of time
        # complaining about WIFI
        # I'm going to ignore 'tries'
        # And I will return None instead

        # Tries should go probably to read_msg
        # to see if the device returns actual values
        # Here we are waiting until we get actual valid data
        logger = logging.getLogger(__name__)
        this_try = 0
        while this_try < tries:
            msg = self.read_msg()
            # logger.debug("msg is %s", msg)
            try:
                res = json.loads(msg)
            except ValueError:
                res = None
            # Sometimes it returns numbers, not dicts
            if res and isinstance(res, dict):
                logger.debug("process message")
                pmsg = self.process_msg(res)
                logger.debug("processed data is %s", pmsg)
                return pmsg
            else:
                # We expect several non-json messages between correct msgs
                return None

        return None

    def process_msg(self, res: typing.Mapping) -> dict:
        """Convert the message from the photometer to unified format"""
        # temps
        # Convert whatever we read from the photometer
        # to a unified format
        payload = dict()
        payload["model"] = "TESSv2"
        payload["cmd"] = "r"
        payload["protocol_revision"] = 2
        payload["zero_point"] = self.calibration
        payload["name"] = self.name

        msg_zp = res.get("ZP")
        if self.calibration != msg_zp:
            msg = "Calibration values don't agree: self:{} payload:{}".format(self.calibration, msg_zp)
            warnings.warn(msg, RuntimeWarning)

        msg_rev = res.get("rev")
        if msg_rev != 2:
            msg = "Protocol values don't agree: self:{} payload:{}".format(2, msg_rev)
            warnings.warn(msg, RuntimeWarning)

        # Actual lectures from the photometer
        freq = res.get("freq")  # Actual measurement, in Hz
        mag = res.get("mag")
        if freq is None or mag is None:
            _logger.warning("message without freq or mag, ignoring %s", res)
            return None
        payload["freq_sensor"] = freq
        payload["magnitude"] = mag
        payload["valid"] = True
        # Temperatures are optional
        for key, msg_key in [("temp_ambient", "tamb"), ("temp_sky", "tsky")]:
            if res.get(msg_key) is not None:
                payload[key] = res[msg_key]

        # Add time information
        payload["tstamp"] = datetime.datetime.utcnow()
        return payload
