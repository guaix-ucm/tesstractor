# PySQM main program
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

import os
import datetime
import time
import logging

import pysqm.read
import pysqm.plot
import pysqm.common
import pysqm.observatory as obs
import pysqm.save


def loop(config, mydevice):

    logger = logging.getLogger('pysqm')

    datastore = pysqm.save.DataStore(config, mydevice)

    # Ephem is used to calculate moon position (if above horizon)
    # and to determine start-end times of the measures
    observ = obs.define_ephem_observatory(config=config)
    niter = 0
    DaytimePrint = True
    logger.info('Starting readings ...')

    while True:
        # The programs works as a daemon
        utcdt = obs.read_datetime()
        # print (str(mydevice.local_datetime(utcdt))),
        if obs.is_nighttime(observ, config._observatory_horizon):
            # If we are in a new night, create the new file.
            config._send_to_datacenter = False  ### Not enabled by default
            if config._send_to_datacenter and (niter == 0):
                pysqm.save.save_data_datacenter("NEWFILE", config, mydevice)

            StartDateTime = datetime.datetime.now()
            niter += 1

            datastore.define_filenames(config)

            # Get values from the photometer
            try:
                data = mydevice.read_photometer(dtz=config._local_timezone,
                                                Nmeasures=config._measures_to_promediate,
                                                PauseMeasures=10
                                                )
            except StandardError as error:
                logger.error('Connection lost, %s', error, exc_info=True)
                # FIXME: not appropriated in all cases
                if config._reboot_on_connlost:
                    time.sleep(600)
                    os.system('reboot.bat')

                time.sleep(1)
                mydevice.reset_device()
                continue

            (timeutc_mean, timelocal_mean, temp_sensor,
             freq_sensor, ticks_uC, sky_brightness) = data

            formatted_data = pysqm.save.format_content(
                timeutc_mean,
                timelocal_mean,
                temp_sensor,
                freq_sensor,
                ticks_uC,
                sky_brightness
            )

            if config._use_mysql:
                pysqm.save.save_data_mysql(formatted_data, config)

            if config._send_to_datacenter:
                pysqm.save.save_data_datacenter(formatted_data, config, mydevice)

            mydevice.data_cache(formatted_data, datastore,
                                number_measures=config._cache_measures,
                                niter=niter)

            if niter % config._plot_each == 0:
                # Each X minutes, plot a new graph
                try:
                    pysqm.plot.make_plot(config, send_emails=False, write_stats=False)
                except StandardError:
                    logger.warn('Problem plotting data.', exc_info=True)

            if not DaytimePrint:
                DaytimePrint = True

            MainDeltaSeconds = (datetime.datetime.now() - StartDateTime).total_seconds()
            time.sleep(max(1, config._delay_between_measures - MainDeltaSeconds))

        else:
            # Daytime, print info
            if DaytimePrint:
                utcdt = utcdt.strftime("%Y-%m-%d %H:%M:%S")
                logger.info("%s", utcdt)
                logger.info('Daytime. Waiting until %s', obs.next_sunset(observ, config._observatory_horizon))
                DaytimePrint = False
            if niter > 0:
                mydevice.flush_cache(datastore)
                if config._send_data_by_email:
                    try:
                        pysqm.plot.make_plot(config, send_emails=True, write_stats=True)
                    except StandardError:
                        logger.warn('Error plotting data / sending email.',exc_info=True)

                else:
                    try:
                        pysqm.plot.make_plot(config, send_emails=False, write_stats=True)
                    except StandardError:
                        logger.warn('Problem plotting data.', exc_info=True)

                niter = 0

            # Send data that is still in the datacenter buffer
            if config._send_to_datacenter:
                pysqm.save.save_data_datacenter("", config, mydevice)

            time.sleep(300)


def init_sqm_lu(config):
    logger = logging.getLogger('pysqm')
    try:
        logger.info('Trying fixed device address %s ... ', config._device_addr)
        mydevice = pysqm.read.SQMLU(addr=config._device_addr)
        return mydevice
    except StandardError:
        logger.warn('Device not found in %s', config._device_addr)

    logger.info('Trying auto device address ...')
    autodev = pysqm.read.SQMLU.search(bauds=115200)
    if autodev is None:
        logger.error('Device not found!')
        return None

    logger.info('Found address %s ... ', autodev)
    try:
        mydevice = pysqm.read.SQMLU(addr=autodev)
        return mydevice
    except StandardError:
        logger.error('Device not found!')
        return None


def init_sqm_le(config):
    logger = logging.getLogger('pysqm')
    try:
        logger.info('Trying fixed device address %s ... ', config._device_addr)
        mydevice = pysqm.read.SQMLE(addr=config._device_addr)
        return mydevice
    except StandardError:
        logger.warn('Device not found in %s', config._device_addr)

    logger.info('Trying auto device address ...')
    autoaddr = pysqm.read.SQMLU.search()
    if autoaddr is None:
        logger.error('Device not found!')
        return None

    logger.info('Found address %s ... ', autoaddr)
    try:
        mydevice = pysqm.read.SQMLU(addr=autoaddr)
        return mydevice
    except StandardError:
        logger.error('Device not found!')
        return None


def  main():
    import argparse
    # import ConfigParser
    import pysqm.settings as settings

    logging.basicConfig(level=logging.DEBUG)

    logger = logging.getLogger('pysqm')

    parser = argparse.ArgumentParser(description="Python client for the Sky Quality Meter ")
    parser.add_argument('-c', '--config', default="config.py", help="configuration file")
    args = parser.parse_args()

    configfilename = args.config
    logger.debug("Using configuration file: %s", configfilename)

    # New instance with 'bar' and 'baz' defaulting to 'Life' and 'hard' each
    # config = ConfigParser.SafeConfigParser({'bar': 'Life', 'baz': 'hard'})
    # config.read('config.ini')

    # print config.get('site', 'observatory_name') # -> "Python is fun!"
    # print config.get('paths', 'daily_graph_directory') # -> "Life is hard!"

    # Load config contents into GlobalConfig
    settings.GlobalConfig.read_config_file(configfilename)

    # Get the actual config
    config = settings.GlobalConfig.config
    # Conditional imports

    # If the old format (SQM_LE/SQM_LU) is used, replace _ with -
    config._device_type = config._device_type.replace('_', '-')


    # Create directories if needed
    for directory in [config.monthly_data_directory,
                      config.daily_data_directory,
                      config.current_data_directory,
                      config.daily_graph_directory,
                      config.current_graph_directory
                      ]:
        if not os.path.exists(directory):
            logger.debug('Create directory %s', directory)
            os.makedirs(directory)

    # Select the device to be used based on user input
    # and start the measures

    if config._device_type == 'SQM-LU':
        mydevice = init_sqm_lu(config)
        if mydevice is None:
            return 1

    elif config._device_type == 'SQM-LE':
        mydevice = init_sqm_le(config)
        if mydevice is None:
            return 1

    else:
        logger.error('Unknown device type %s', config._device_type)
        return 1

    while(True):
        # Loop forever to make sure the program does not die.
        #try:
        loop(config, mydevice)
        # except Exception as e:
        #     print('')
        #     print('FATAL ERROR while running the main loop !!')
        #     print('Error was:')
        #     print(e)
        #     print('Trying to restart')
        #     print('')

