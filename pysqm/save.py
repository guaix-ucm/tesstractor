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


import os
import shutil
import datetime

import pysqm.common
import pysqm.observatory as obs


def standard_file_header(config, device):
    # Data Header, at the end of this script.
    header_content = pysqm.common.RAWHeaderContent

    # Update data file header with observatory data
    header_content = header_content.replace(
        '$DEVICE_TYPE', str(config._device_type))
    header_content = header_content.replace(
        '$DEVICE_ID', str(config._device_id))
    header_content = header_content.replace(
        '$DATA_SUPPLIER', str(config._data_supplier))
    header_content = header_content.replace(
        '$LOCATION_NAME', str(config._device_locationname))
    header_content = header_content.replace(
        '$OBSLAT', str(config._observatory_latitude))
    header_content = header_content.replace(
        '$OBSLON', str(config._observatory_longitude))
    header_content = header_content.replace(
        '$OBSALT', str(config._observatory_altitude))
    header_content = header_content.replace(
        '$OFFSET', str(config._offset_calibration))

    if config._local_timezone == 0:
        header_content = header_content.replace(
            '$TIMEZONE', 'UTC')
    elif config._local_timezone > 0:
        header_content = header_content.replace(
            '$TIMEZONE', 'UTC+' + str(config._local_timezone))
    elif config._local_timezone < 0:
        header_content = header_content.replace(
            '$TIMEZONE', 'UTC' + str(config._local_timezone))

    header_content = header_content.replace(
        '$PROTOCOL_NUMBER', str(device.protocol_number))
    header_content = header_content.replace(
        '$MODEL_NUMBER', str(device.model_number))
    header_content = header_content.replace(
        '$FEATURE_NUMBER', str(device.feature_number))
    header_content = header_content.replace(
        '$SERIAL_NUMBER', str(device.serial_number))

    header_content = header_content.replace(
        '$IXREADOUT', pysqm.common.remove_linebreaks(device.ix_readout))
    header_content = header_content.replace(
        '$RXREADOUT', pysqm.common.remove_linebreaks(device.rx_readout))
    header_content = header_content.replace(
        '$CXREADOUT', pysqm.common.remove_linebreaks(device.cx_readout))

    return header_content


def format_content(timeutc_mean, timelocal_mean, temp_sensor,
                   freq_sensor, ticks_uC, sky_brightness):
    # Format a string with data
    date_time_utc_str = str(
        timeutc_mean.strftime("%Y-%m-%dT%H:%M:%S")) + '.000'
    date_time_local_str = str(
        timelocal_mean.strftime("%Y-%m-%dT%H:%M:%S")) + '.000'
    temp_sensor_str = str('%.2f' % temp_sensor)
    ticks_uC_str = str('%.3f' % ticks_uC)
    freq_sensor_str = str('%.3f' % freq_sensor)
    sky_brightness_str = str('%.3f' % sky_brightness)

    formatted_data = \
        date_time_utc_str + ";" + date_time_local_str + ";" + temp_sensor_str + ";" + \
        ticks_uC_str + ";" + freq_sensor_str + ";" + sky_brightness_str + "\n"

    return formatted_data


def save_data_datacenter(formatted_data, config, device):
    """This function sends the data from this pysqm client to the central
    node @ UCM. It saves the data there (only the SQM data file contents)
    """

    import socket

    # Connection details (hardcoded to avoid user changes)
    DC_HOST = "muon.gae.ucm.es"
    DC_PORT = 8739
    DEV_ID = "%s_%s" % (config._device_id, device.serial_number)

    def send_data(data):
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect((DC_HOST, DC_PORT))
            client.sendall(data)
            client.shutdown(socket.SHUT_RDWR)
            client.close()
        except:
            return 0
        else:
            return 1

    def write_buffer():
        success = 0
        for data_line in device.DataBuffer[:]:
            success = send_data(DEV_ID + ";;D;;" + data_line)
            if (success == 1):
                device.DataBuffer.remove(data_line)

        return success

    # Send the new file initialization to the datacenter
    # Appends the header to the buffer (it will be sent later)

    if formatted_data == "NEWFILE":
        device.DataBuffer = [hl + "\n" for hl in device.standard_file_header().split("\n")[:-1]]

        # Try to connect with the datacenter and send the header
        success = send_data(DEV_ID + ";;C;;")
        success = write_buffer()
        return (success)
    else:
        # Send the data to the datacenter

        # If the buffer is full, dont append more data.
        if (len(device.DataBuffer) < 10000):
            device.DataBuffer.append(formatted_data)

        # Try to connect with the datacenter and send the data
        success = write_buffer()
        return success


def save_data_mysql(formatted_data, config):
    """
    Use the Python MySQL API to save the
    data to a database
    """

    import MySQLdb
    import inspect

    mydb = None
    values = formatted_data.split(';')
    try:
        # Start database connection
        mydb = MySQLdb.connect(
            host=config._mysql_host,
            user=config._mysql_user,
            passwd=config._mysql_pass,
            db=config._mysql_database,
            port=config._mysql_port)

        # Insert the data
        # FIXME: mysql injection possible
        mydb.query(
            "INSERT INTO " + str(config._mysql_dbtable) + " VALUES (NULL,'" + \
            values[0] + "','" + values[1] + "'," + \
            values[2] + "," + values[3] + "," + \
            values[4] + "," + values[5] + ")")
    except Exception as ex:
        print(str(inspect.stack()[0][2:4][::-1]) +
              ' DB Error. Exception: %s' % str(ex))

    if mydb:
        mydb.close()


class DataStore(object):

    def __init__(self, config, device):
        self.monthly_datafile = ""
        self.daily_datafile = ""
        self.current_datafile = ""

        self.header = standard_file_header(config, device)

        self.define_filenames(config)

    def define_filenames(self, config):

        # Filenames should follow a standard based on observatory name and date.
        date_time_file = obs.local_datetime(obs.read_datetime(), config._local_timezone) - datetime.timedelta(hours=12)
        date_file = date_time_file.date()
        yearmonth = str(date_file)[0:7]
        yearmonthday = str(date_file)[0:10]


        mf = "%s_%s_%s.dat" % (config._device_shorttype, config._observatory_name, yearmonth)
        self.monthly_datafile = os.path.join(config.monthly_data_directory, mf)

        df = "%s_120000_%s-%s.dat" % (yearmonthday.replace('-', ''), config._device_shorttype, config._observatory_name)
        self.daily_datafile = os.path.join(config.daily_data_directory, df)

        cf = "%s_%s.dat" % (config._device_shorttype, config._observatory_name)
        self.current_datafile = os.path.join(config.current_data_directory, cf)

    def save_data(self, formatted_data):
        '''
        Save data to file and duplicate to current
        data file (the one that will be ploted)
        '''
        for each_file in [self.monthly_datafile, self.daily_datafile]:
            if not os.path.exists(each_file):
                with open(each_file, 'w') as datafile:
                    datafile.write(self.header)

            with open(each_file, 'a+') as datafile:
                datafile.write(formatted_data)

        shutil.copyfile(self.daily_datafile, self.current_datafile)



