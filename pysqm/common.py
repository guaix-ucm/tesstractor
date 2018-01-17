# PySQM common code
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


def remove_linebreaks(data):
    # Remove line breaks from data
    data = data.replace('\r\n','')
    data = data.replace('\r','')
    data = data.replace('\n','')
    return data

def format_value(data,remove_str=' '):
    # Remove string and spaces from data
    data = remove_linebreaks(data)
    data = data.replace(remove_str,'')
    data = data.replace(' ','')
    return data

def format_value_list(data,remove_str=' '):
    # Remove string and spaces from data array/list
    data = [format_value(line,remove_str).split(';') for line in data]
    return data


RAWHeaderContent = '''# Definition of the community standard for skyglow observations 1.0
# URL: http://www.darksky.org/NSBM/sdf1.0.pdf
# Number of header lines: 35
# This data is released under the following license: ODbL 1.0 http://opendatacommons.org/licenses/odbl/summary/
# Device type: $DEVICE_TYPE
# Instrument ID: $DEVICE_ID
# Data supplier: $DATA_SUPPLIER
# Location name: $LOCATION_NAME
# Position: $OBSLAT, $OBSLON, $OBSALT
# Local timezone: $TIMEZONE
# Time Synchronization: NTP
# Moving / Stationary position: STATIONARY
# Moving / Fixed look direction: FIXED
# Number of channels: 1
# Filters per channel: HOYA CM-500
# Measurement direction per channel: 0., 0.
# Field of view: 20
# Number of fields per line: 6
# SQM serial number: $SERIAL_NUMBER
# SQM firmware version: $FEATURE_NUMBER
# SQM cover offset value: $OFFSET
# SQM readout test ix: $IXREADOUT
# SQM readout test rx: $RXREADOUT
# SQM readout test cx: $CXREADOUT
# Comment:
# Comment:
# Comment:
# Comment:
# Comment: Capture program: PySQM
# blank line 30
# blank line 31
# blank line 32
# UTC Date & Time, Local Date & Time, Temperature, Counts, Frequency, MSAS
# YYYY-MM-DDTHH:mm:ss.fff;YYYY-MM-DDTHH:mm:ss.fff;Celsius;number;Hz;mag/arcsec^2
# END OF HEADER
'''
