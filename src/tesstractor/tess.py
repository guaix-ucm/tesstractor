#
# Copyright 2018-2024 Universidad Complutense de Madrid
#
# This file is part of tesstractor
#
# SPDX-License-Identifier: GPL-3.0-or-later
# License-Filename: LICENSE.txt
#


import logging
import re
import math
import datetime
import json
import typing

from .device import Device, LineReader, PhotometerConf

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


# MAC used to register in MQTT if it is not in the configuration
UNKNOWN_MAC = "01:23:45:67:89:AB"

# The TESSv2 measures the period in microseconds, it saturates at 1e6 / 9 Hz
# and sends 111111.11
TESSV2_FREQ_MAX = 111111.0

_logger = logging.getLogger(__name__)


def _is_number(value) -> bool:
    """Check that a value from a JSON message is a finite number"""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


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

        # Only known if it is in the configuration
        self.mac = None
        self.cmd_wait = 0
        self.counts = 1

    def static_conf(self):
        conf = TESSConf()
        conf.name = self.serial_number
        conf.model = self.model
        conf.serial_number = self.serial_number
        conf.zero_point = self.calibration
        # The TESS does not report its MAC and firmware
        conf.mac_address = self.mac or ""
        return conf

    def register_id(self):
        """ID used for registration"""
        return self.mac or UNKNOWN_MAC

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
        result["tstamp"] = datetime.datetime.now(datetime.UTC)

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
                if msg:
                    logger.warning("malformed data, ignoring %s", msg)
                else:
                    logger.debug("no data before timeout")
                this_try += 1

        msg = f"no valid data after {tries} tries, check the port and the baud rate"
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
                if msg:
                    logger.warning("malformed data, ignoring %s", msg)
                else:
                    logger.debug("no data before timeout")
                # The device sends lines continuously, the next
                # line is in sync, there is no need to reset
                this_try += 1

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
        self.lines = LineReader(conn)

    def start_connection(self):
        """Start photometer connection"""
        _logger.debug("start connection")
        self.lines.reset()

        self.read_metadata(tries=10)
        self.read_calibration(tries=10)
        self.read_data(tries=10)

    def reset_device(self):
        """Discard pending input, reopening the port if needed"""
        _logger.debug("reset device")
        self.lines.reset()

    def close_connection(self):
        """End photometer connection"""
        # Check until there is no answer from device
        _logger.debug("close connection")
        self.serial.close()

    def read_msg(self):
        """Read the data"""
        msg = self.lines.readline()
        return msg

    def pass_command(self, cmd):
        self.serial.write(cmd)


class TessV2(Tess):
    """TESS serial V2

    The photometer sends a JSON message each second, with these fields:

    {
    "udp":83471,  output number, ignored
    "rev":2,  protocol revision
    "name":"stars605",
    "freq":13.38,  in Hz
    "mag":17.52,
    "tamb":30.39,
    "tsky":29.23,
    "wdBm":-50,  wifi power, ignored
    "hash":"988",  ignored
    "ain":448,  analog input, ignored
    "ZP":20.34  zero_point
    }

    Between them it sends empty lines, counters (numbers)
    and text messages, that are ignored.
    """

    def __init__(self, conn, name=None, zero_point=None):
        super().__init__(name=name, model="TESSv2")
        self.serial = conn
        self.lines = LineReader(conn)
        # Values from the configuration, the photometer reports its own
        self.conf_name = name
        self.conf_zero_point = zero_point

    def start_connection(self, tries=30):
        """Start photometer connection, read the name and zero point"""
        _logger.debug("start connection")
        self.lines.reset()

        for _ in range(tries):
            res = self.parse_line(self.read_msg())
            if (
                res is not None
                and isinstance(res.get("name"), str)
                and all(_is_number(res.get(key)) for key in ["ZP", "freq", "mag"])
            ):
                break
        else:
            msg = f"no valid data after {tries} tries, check the port and the baud rate"
            _logger.error(msg)
            raise ValueError(msg)

        self.name = self.serial_number = res["name"]
        self.calibration = res["ZP"]
        _logger.info("photometer %s, zero point %s", self.name, self.calibration)
        if self.conf_name is not None and self.conf_name != self.name:
            _logger.warning("name in the configuration is %s, using %s from the photometer", self.conf_name, self.name)
        if self.conf_zero_point is not None and self.conf_zero_point != self.calibration:
            _logger.warning(
                "zero_point in the configuration is %s, using %s from the photometer",
                self.conf_zero_point,
                self.calibration,
            )

    def close_connection(self):
        """End photometer connection"""
        _logger.debug("close connection")
        self.serial.close()

    def read_msg(self):
        """Read messages from the photometer"""
        msg = self.lines.readline()
        return msg

    def pass_command(self, cmd):
        # We can't pass commands
        pass

    def read_metadata(self, tries=1):
        # The metadata is read in start_connection
        pass

    @staticmethod
    def parse_line(msg: bytes) -> dict | None:
        """Return the JSON message in the line, None if there is none"""
        try:
            res = json.loads(msg)
        except ValueError:
            return None
        # Counters are numbers, not dicts
        if isinstance(res, dict):
            return res
        return None

    def read_data(self, tries=1):
        """Read measurements"""
        for _ in range(tries):
            msg = self.read_msg()
            res = self.parse_line(msg)
            if res is None:
                # Several non JSON lines are expected between measurements
                _logger.debug("ignoring %s", msg)
                continue
            pmsg = self.process_msg(res)
            _logger.debug("processed data is %s", pmsg)
            return pmsg

        _logger.debug("no measurement after %d lines", tries)
        return None

    def process_msg(self, res: typing.Mapping) -> dict | None:
        """Convert the message from the photometer to unified format"""
        freq = res.get("freq")  # Actual measurement, in Hz
        mag = res.get("mag")
        # Lines cut or joined can be valid JSON with wrong values
        if not (_is_number(freq) and _is_number(mag)):
            _logger.warning("message without valid freq or mag, ignoring %s", res)
            return None

        payload = dict()
        payload["model"] = "TESSv2"
        payload["cmd"] = "r"
        payload["protocol_revision"] = res.get("rev", 2)
        payload["name"] = self.name

        msg_zp = res.get("ZP")
        if not _is_number(msg_zp):
            msg_zp = self.calibration
        if msg_zp != self.calibration:
            _logger.warning("zero point of the photometer changed from %s to %s", self.calibration, msg_zp)
            # The file header keeps the initial value
            self.calibration = msg_zp
        payload["zero_point"] = msg_zp

        payload["freq_sensor"] = freq
        payload["magnitude"] = mag
        payload["valid"] = 0 < freq < TESSV2_FREQ_MAX
        if freq >= TESSV2_FREQ_MAX:
            _logger.debug("photometer saturated, freq %s", freq)
        # A photometer without temperature sensors sends 0.00 in both
        tamb, tsky = res.get("tamb"), res.get("tsky")
        if not (tamb == 0 and tsky == 0):
            for key, value in [("temp_ambient", tamb), ("temp_sky", tsky)]:
                if _is_number(value):
                    payload[key] = value

        # Add time information
        payload["tstamp"] = datetime.datetime.now(datetime.UTC)
        return payload
