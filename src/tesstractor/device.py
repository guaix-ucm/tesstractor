#
# Copyright 2018-2024 Universidad Complutense de Madrid
#
# This file is part of tesstractor
#
# SPDX-License-Identifier: GPL-3.0-or-later
# License-Filename: LICENSE.txt
#


# Maximum length of a line from the photometer
MAX_LINE = 1024


def read_line(conn):
    """Read a line from the serial port.

    Serial.readline applies the timeout to each byte, it blocks
    while bytes without a newline keep arriving (for example, with
    a wrong baud rate). read_until applies the timeout to the line.
    """
    # Some ports send NUL bytes after being opened
    return conn.read_until(b"\n", MAX_LINE).lstrip(b"\x00")


class Device:
    """Photometric device"""

    def __init__(self, name="unknown", model="unknown"):
        super().__init__()
        self.name = name
        self.model = model

        self.serial_number = self.name
        self.calibration = 20.5

    def start_connection(self):
        pass

    def static_conf(self):
        pass

    def read_msg(self):
        """Read the photometer"""
        pass

    def process_msg(self, msg):
        pass

    def read_data(self, tries=1):
        """Read measurements.

        Keep trying until it reads actual data
        """

        this_try = 0
        while this_try < tries:
            msg = self.read_msg()
            if msg:
                proc_msg = self.process_msg(msg)
                return proc_msg
            else:
                this_try += 1

        text = f"unable to read data after {tries} tries"
        raise ValueError(text)

    def filter_buffer(self, list_of_payload):
        pass

    def register_id(self):
        return self.serial_number


class PhotometerConf:
    name = "somename"
    model = "somemodel"
    serial_number = 1
    mac_address = "01:23:45:67:89:AB"
    filter = "b"
    azimuth = 0.0
    altitude = 0.0
    fov = 20
    firmware = 29
    cover_offset = -0.11
    zero_point = 29
    ix_readout = ""
    rx_readout = ""
    cx_readout = ""

    @property
    def zenith(self):
        """Zenith angle of the measurement direction"""
        return 90.0 - self.altitude
