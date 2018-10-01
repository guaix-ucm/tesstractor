#
# Copyright 2018 Universidad Complutense de Madrid
#
# This file is part of pysqm-lite
#
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSE.txt
#


class Device:
    def __init__(self, name="unknown", model='unknown'):
        super().__init__()


class PhotometerConf:
    name = 'somename'
    model = 'somemodel'
    serial_number = 1
    mac_address = "01:23:45:67:89:AB"
    filter = 'b'
    azimuth = 0.0
    altitude = 0.0
    fov = 20
    firmware = 29
    cover_offset = -0.11
    zero_point = 29
    ix_readout = ""
    rx_readout = ""
    cx_readout = ""
