# PySQM plotting program
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
import sys
import logging
import datetime
from datetime import timedelta

import ephem
import numpy as np
import matplotlib

matplotlib.use('Agg')
import matplotlib.ticker as ticker
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from pysqm.common import format_value, format_value_list
import pysqm.observatory as obs


class SQMData(object):
    # Split pre and after-midnight data

    class premidnight(object):
        pass

    class aftermidnight(object):
        pass

    class Statistics(object):
        pass

    def __init__(self, filename, Ephem, config):
        self.all_night_sb = []
        self.all_night_dt = []
        self.all_night_temp = []

        for variable in [
            'utcdates', 'localdates', 'sun_altitudes',
            'temperatures', 'tick_counts', 'frequencies',
            'night_sbs', 'label_dates', 'sun_altitude']:
            setattr(self.premidnight, variable, [])
            setattr(self.aftermidnight, variable, [])

        self.load_rawdata(filename)
        self.process_rawdata(Ephem, tz=config._local_timezone)
        self.check_number_of_nights()

    def extract_metadata(self, raw_data_and_metadata):
        metadata_lines = [line for line in raw_data_and_metadata if format_value(line)[0] == '#']

        # Extract the serial number
        serial_number_line = [line for line in metadata_lines if 'SQM serial number:' in line][0]
        self.serial_number = format_value(serial_number_line.split(':')[-1])

    def check_validdata(self, data_line):
        if (format_value(data_line)[0] != '#') and (format_value(data_line)[0] != ''):
            return True
        else:
            return False

    def load_rawdata(self, filename):
        '''
        Open the file, read the data and close the file
        '''
        with open(filename, 'r') as sqm_file:
            raw_data_and_metadata = sqm_file.readlines()
            self.metadata = self.extract_metadata(raw_data_and_metadata)

            self.raw_data = [ \
                line for line in raw_data_and_metadata \
                if self.check_validdata(line) == True]

    def process_datetimes(self, str_datetime):
        '''
        Get date and time in a str format
        Return as datetime object
        '''
        str_date, str_time = str_datetime.split('T')

        year = int(str_date.split('-')[0])
        month = int(str_date.split('-')[1])
        day = int(str_date.split('-')[2])

        # Time may be not complete. Workaround
        hour = int(str_time.split(':')[0])
        try:
            minute = int(str_time.split(':')[1])
        except ValueError:
            minute = 0
            second = 0
        else:
            try:
                second = int(str_time.split(':')[2])
            except ValueError:
                second = 0

        return datetime.datetime(year, month, day, hour, minute, second)

    def process_rawdata(self, Ephem, tz):
        '''
        Get the important information from the raw_data
        and put it in a more useful format
        '''
        self.raw_data = format_value_list(self.raw_data)

        for k, line in enumerate(self.raw_data):
            # DateTime extraction
            utcdatetime = self.process_datetimes(line[0])
            localdatetime = self.process_datetimes(line[1])

            # Check that datetimes are corrent
            calc_localdatetime = utcdatetime + timedelta(hours=tz)
            # assert (calc_localdatetime == localdatetime)

            # Set the datetime for astronomical calculations.
            Ephem.Observatory.date = ephem.date(utcdatetime)

            # Date in str format: 20130115
            label_date = str(localdatetime.date()).replace('-', '')

            # Temperature
            temperature = float(line[2])
            # Counts
            tick_counts = float(line[3])
            # Frequency
            frequency = float(line[4])
            # Night sky background
            night_sb = float(line[5])
            # Define sun in pyephem
            Sun = ephem.Sun(Ephem.Observatory)

            self.premidnight.label_date = []
            self.aftermidnight.label_dates = []

            if localdatetime.hour > 12:
                self.premidnight.utcdates.append(utcdatetime)
                self.premidnight.localdates.append(localdatetime)
                self.premidnight.temperatures.append(temperature)
                self.premidnight.tick_counts.append(tick_counts)
                self.premidnight.frequencies.append(frequency)
                self.premidnight.night_sbs.append(night_sb)
                self.premidnight.sun_altitude.append(Sun.alt)
                if label_date not in self.premidnight.label_dates:
                    self.premidnight.label_dates.append(label_date)
            else:
                self.aftermidnight.utcdates.append(utcdatetime)
                self.aftermidnight.localdates.append(localdatetime)
                self.aftermidnight.temperatures.append(temperature)
                self.aftermidnight.tick_counts.append(tick_counts)
                self.aftermidnight.frequencies.append(frequency)
                self.aftermidnight.night_sbs.append(night_sb)
                self.aftermidnight.sun_altitude.append(Sun.alt)
                if label_date not in self.aftermidnight.label_dates:
                    self.aftermidnight.label_dates.append(label_date)

            # Data for the complete night
            self.all_night_dt.append(utcdatetime)  # Must be in UTC!
            self.all_night_sb.append(night_sb)
            self.all_night_temp.append(temperature)

    def check_number_of_nights(self):
        '''
        Check that the number of nights is exactly 1 and
        extract it to a new variable self.Night.
        Needed for the statistics part of the analysis and
        to make the plot.
        '''

        logger = logging.getLogger(__name__)

        if np.size(self.premidnight.localdates) > 0:
            self.Night = np.unique([DT.date() for DT in self.premidnight.localdates])[0]
        elif np.size(self.aftermidnight.localdates) > 0:
            self.Night = np.unique([(DT - datetime.timedelta(hours=12)).date()
                                    for DT in self.aftermidnight.localdates])[0]
        else:
            logger.warn('No Night detected.')
            self.Night = None

    def data_statistics(self, Ephem):
        '''
        Make statistics on the data.
        Useful to summarize night conditions.
        '''

        logger = logging.getLogger(__name__)

        def select_bests(values, number):
            return (np.sort(values)[::-1][0:number])

        def fourier_filter(array, nterms):
            '''
            Make a fourier filter for the first nterms terms.
            '''
            array_fft = np.fft.fft(array)
            # Filter data
            array_fft[nterms:] = 0
            filtered_array = np.fft.ifft(array_fft)
            return (filtered_array)

        astronomical_night_filter = (
            (np.array(self.all_night_dt) > Ephem.twilight_prev_set) *
            (np.array(self.all_night_dt) < Ephem.twilight_next_rise)
        )

        if np.sum(astronomical_night_filter) > 10:
            self.astronomical_night_sb = \
                np.array(self.all_night_sb)[astronomical_night_filter]
            self.astronomical_night_temp = \
                np.array(self.all_night_temp)[astronomical_night_filter]
        else:
            logger.warn('< 10 points in astronomical night, using the whole night data instead')
            self.astronomical_night_sb = self.all_night_sb
            self.astronomical_night_temp = self.all_night_temp

        stat = self.Statistics
        # with self.Statistics as Stat:
        # Complete list
        stat.mean = np.mean(self.astronomical_night_sb)
        stat.median = np.median(self.astronomical_night_sb)
        stat.std = np.median(self.astronomical_night_sb)
        stat.number = np.size(self.astronomical_night_sb)
        # Only the best 1/100th.
        stat.bests_number = int(1 + stat.number / 50.)
        stat.bests_mean = np.mean(select_bests(self.astronomical_night_sb, stat.bests_number))
        stat.bests_median = np.median(select_bests(self.astronomical_night_sb, stat.bests_number))
        stat.bests_std = np.std(select_bests(self.astronomical_night_sb, stat.bests_number))
        stat.bests_err = stat.bests_std * 1. / np.sqrt(stat.bests_number)

        stat.model_nterm = stat.bests_number
        data_smooth = fourier_filter(self.astronomical_night_sb, nterms=stat.model_nterm)
        data_residuals = self.astronomical_night_sb - data_smooth
        stat.data_model_abs_meandiff = np.mean(np.abs(data_residuals))

        # Other interesting data
        stat.min_temperature = np.min(self.astronomical_night_temp)
        stat.max_temperature = np.max(self.astronomical_night_temp)


class Plot(object):
    def __init__(self, Data, Ephem, config):
        plt.hold(True)
        Data = self.prepare_plot(Data, Ephem)

        if config.full_plot:
            self.make_figure(config, thegraph_altsun=True, thegraph_time=True)
            self.plot_data_sunalt(Data, Ephem, config=config)
        else:
            self.make_figure(config, thegraph_altsun=False, thegraph_time=True)

        self.plot_data_time(Data, Ephem, config=config)

        self.plot_moonphase(Ephem, tz=config._local_timezone)
        self.plot_twilight(Ephem, tz=config._local_timezone)
        plt.hold(False)

    def plot_moonphase(self, Ephem, tz):
        '''
        shade the period of time for which the moon is above the horizon
        '''
        if Ephem.moon_next_rise > Ephem.moon_next_set:
            # We need to divide the plotting in two phases
            # (pre-midnight and after-midnight)
            self.thegraph_time.axvspan(
                Ephem.moon_prev_rise + datetime.timedelta(hours=tz),
                Ephem.moon_next_set + datetime.timedelta(hours=tz),
                edgecolor='r', facecolor='r', alpha=0.1, clip_on=True)
        else:
            self.thegraph_time.axvspan(
                Ephem.moon_prev_rise + datetime.timedelta(hours=tz),
                Ephem.moon_prev_set + datetime.timedelta(hours=tz),
                edgecolor='r', facecolor='r', alpha=0.1, clip_on=True)
            self.thegraph_time.axvspan(
                Ephem.moon_next_rise + datetime.timedelta(hours=tz),
                Ephem.moon_next_set + datetime.timedelta(hours=tz),
                edgecolor='r', facecolor='r', alpha=0.1, clip_on=True)

    def plot_twilight(self, Ephem, tz):
        '''
        Plot vertical lines on the astronomical twilights
        '''
        self.thegraph_time.axvline(
            Ephem.twilight_prev_set + datetime.timedelta(hours=tz),
            color='k', ls='--', lw=2, alpha=0.5, clip_on=True)
        self.thegraph_time.axvline(
            Ephem.twilight_next_rise + datetime.timedelta(hours=tz),
            color='k', ls='--', lw=2, alpha=0.5, clip_on=True)

    def make_subplot_sunalt(self, config, twinplot=0):
        '''
        Make a subplot.
        If twinplot = 0, then this will be the only plot in the figure
        if twinplot = 1, this will be the first subplot
        if twinplot = 2, this will be the second subplot
        '''
        if twinplot is 0:
            self.thegraph_sunalt = self.thefigure.add_subplot(1, 1, 1)
        else:
            self.thegraph_sunalt = self.thefigure.add_subplot(2, 1, twinplot)

        title = 'Sky Brightness (%s-%s)\n' % (config._device_shorttype, config._observatory_name)
        self.thegraph_sunalt.set_title(title, fontsize='x-large')
        self.thegraph_sunalt.set_xlabel('Solar altitude (deg)', fontsize='large')
        self.thegraph_sunalt.set_ylabel('Sky Brightness (mag/arcsec2)', fontsize='medium')

        # Auxiliary plot (Temperature)
        # self.thegraph_sunalt_temp = self.thegraph_sunalt.twinx()
        # self.thegraph_sunalt_temp.set_ylim(-10, 50)
        # self.thegraph_sunalt_temp.set_ylabel('Temperature (C)',fontsize='medium')

        # format the ticks (frente a alt sol)
        tick_values = range(config.limits_sunalt[0], config.limits_sunalt[1] + 5, 5)
        tick_marks = np.multiply([deg for deg in tick_values], np.pi / 180.0)
        tick_labels = [str(deg) for deg in tick_values]

        self.thegraph_sunalt.set_xticks(tick_marks)
        self.thegraph_sunalt.set_xticklabels(tick_labels)
        self.thegraph_sunalt.yaxis.set_minor_locator(ticker.MultipleLocator(0.5))
        self.thegraph_sunalt.grid(True, which='major')
        self.thegraph_sunalt.grid(True, which='minor')

    def make_subplot_time(self, config, twinplot=0):
        '''
        Make a subplot.
        If twinplot = 0, then this will be the only plot in the figure
        if twinplot = 1, this will be the first subplot
        if twinplot = 2, this will be the second subplot
        '''
        if twinplot is 0:
            self.thegraph_time = self.thefigure.add_subplot(1, 1, 1)
        else:
            self.thegraph_time = self.thefigure.add_subplot(2, 1, twinplot)

        if config._local_timezone < 0:
            UTC_offset_label = '-%s' % abs(config._local_timezone)
        elif config._local_timezone > 0:
            UTC_offset_label = '+%s' % abs(config._local_timezone)
        else:
            UTC_offset_label = ''

        # self.thegraph_time.set_title('Sky Brightness (SQM-'+config._observatory_name+')',\
        # fontsize='x-large')
        xlabel = 'Time (UTC%s)' % UTC_offset_label
        self.thegraph_time.set_xlabel(xlabel, fontsize='large')
        self.thegraph_time.set_ylabel('Sky Brightness (mag/arcsec2)', fontsize='medium')

        # Auxiliary plot (Temperature)

        # self.thegraph_time_temp = self.thegraph_time.twinx()
        # self.thegraph_time_temp.set_ylim(-10, 50)
        # self.thegraph_time_temp.set_ylabel('Temperature (C)',fontsize='medium')

        # format the ticks (vs time)
        daylocator = mdates.HourLocator(byhour=[4, 20])
        hourlocator = mdates.HourLocator()
        dayFmt = mdates.DateFormatter('\n%d %b %Y')
        hourFmt = mdates.DateFormatter('%H')

        self.thegraph_time.xaxis.set_major_locator(daylocator)
        self.thegraph_time.xaxis.set_major_formatter(dayFmt)
        self.thegraph_time.xaxis.set_minor_locator(hourlocator)
        self.thegraph_time.xaxis.set_minor_formatter(hourFmt)
        self.thegraph_time.yaxis.set_minor_locator(ticker.MultipleLocator(0.5))

        self.thegraph_time.format_xdata = mdates.DateFormatter('%Y-%m-%d_%H:%M:%S')
        self.thegraph_time.grid(True, which='major', ls='')
        self.thegraph_time.grid(True, which='minor')

    def make_figure(self, config, thegraph_altsun=True, thegraph_time=True):
        # Make the figure and the graph
        if thegraph_time == False:
            self.thefigure = plt.figure(figsize=(7, 3.))
            self.make_subplot_sunalt(config, twinplot=0)
        elif thegraph_altsun == False:
            self.thefigure = plt.figure(figsize=(7, 3.))
            self.make_subplot_time(config, twinplot=0)
        else:
            self.thefigure = plt.figure(figsize=(7, 6.))
            self.make_subplot_sunalt(config, twinplot=1)
            self.make_subplot_time(config, twinplot=2)

        # Adjust the space between plots
        plt.subplots_adjust(hspace=0.35)

    def prepare_plot(self, Data, Ephem):
        '''
        Warning! Multiple night plot implementation is pending.
        Until the support is implemented, check that no more than 1 night
        is used
        '''

        logger = logging.getLogger(__name__)

        if np.size(Data.Night) != 1:
            logger.warn('More than 1 night in the data file. Please check it! %d', np.size(Data.Night))

        # Mean datetime
        dts = Data.all_night_dt
        mean_dt = dts[0] + np.sum(np.array(dts) - dts[0]) / np.size(dts)
        sel_night = (mean_dt - datetime.timedelta(hours=12)).date()

        Data.premidnight.filter = np.array(
            [Date.date() == sel_night for Date in Data.premidnight.localdates])
        Data.aftermidnight.filter = np.array(
            [(Date - datetime.timedelta(days=1)).date() == sel_night
             for Date in Data.aftermidnight.localdates])

        return Data

    def plot_data_sunalt(self, Data, Ephem, config):
        '''
        Plot NSB data vs Sun altitude
        '''
        # Plot the data
        TheData = Data.premidnight
        if np.size(TheData.filter) > 0:
            self.thegraph_sunalt.plot(
                np.array(TheData.sun_altitude)[TheData.filter],
                np.array(TheData.night_sbs)[TheData.filter], color='g')

            # self.thegraph_sunalt.plot(\
            #  np.array(TheData.sun_altitude)[TheData.filter],\
            #  np.array(TheData.temperatures)[TheData.filter],color='purple',alpha=0.5))

        TheData = Data.aftermidnight
        if np.size(TheData.filter) > 0:
            self.thegraph_sunalt.plot(
                np.array(TheData.sun_altitude)[TheData.filter],
                np.array(TheData.night_sbs)[TheData.filter], color='b')

            # self.thegraph_sunalt.plot(\
            #  np.array(TheData.sun_altitude)[TheData.filter],\
            #  np.array(TheData.temperatures)[TheData.filter],color='purple',alpha=0.5))

        # Make limits on data range.
        self.thegraph_sunalt.set_xlim([
            config.limits_sunalt[0] * np.pi / 180.,
            config.limits_sunalt[1] * np.pi / 180.])
        self.thegraph_sunalt.set_ylim(config.limits_nsb)

        premidnight_label = str(Data.premidnight.label_dates).replace('[', '').replace(']', '')
        aftermidnight_label = str(Data.aftermidnight.label_dates).replace('[', '').replace(']', '')

        self.thegraph_sunalt.text(0.00, 1.015,
                                  config._device_shorttype + '-' + config._observatory_name + ' ' * 5 + 'Serial #' + str(
                                      Data.serial_number),
                                  color='0.25', fontsize='small', fontname='monospace',
                                  transform=self.thegraph_sunalt.transAxes)

        self.thegraph_sunalt.text(0.75, 0.92, 'PM: ' + premidnight_label,
                                  color='g', fontsize='small', transform=self.thegraph_sunalt.transAxes)
        self.thegraph_sunalt.text(0.75, 0.84, 'AM: ' + aftermidnight_label,
                                  color='b', fontsize='small', transform=self.thegraph_sunalt.transAxes)

        # if np.size(Data.Night)==1:
        #     self.thegraph_sunalt.text(0.75,1.015,'Moon: %d%s (%d%s)' \
        #      %(Ephem.moon_phase, "%", Ephem.moon_maxelev*180./np.pi,"$^\mathbf{o}$"),\
        #      color='r',fontsize='small',fontname='monospace',\
        #      transform = self.thegraph_sunalt.transAxes)

    def plot_data_time(self, Data, Ephem, config):
        '''
        Plot NSB data vs Sun altitude
        '''

        # Plot the data (NSB and temperature)

        logger = logging.getLogger(__name__)

        TheData = Data.premidnight
        if np.size(TheData.filter) > 0:
            self.thegraph_time.plot(
                np.array(TheData.localdates)[TheData.filter],
                np.array(TheData.night_sbs)[TheData.filter], color='g')

            # self.thegraph_time_temp.plot(\
            #  np.array(TheData.localdates)[TheData.filter],\
            #  np.array(TheData.temperatures)[TheData.filter],color='purple',alpha=0.5)

        TheData = Data.aftermidnight
        if np.size(TheData.filter) > 0:
            self.thegraph_time.plot(
                np.array(TheData.localdates)[TheData.filter],
                np.array(TheData.night_sbs)[TheData.filter], color='b')

            # self.thegraph_time_temp.plot(\
            #  np.array(TheData.localdates)[TheData.filter],\
            #  np.array(TheData.temperatures)[TheData.filter],color='purple',alpha=0.5)

        # Vertical line to mark 0h
        self.thegraph_time.axvline(
            Data.Night + datetime.timedelta(days=1), color='k', alpha=0.5, clip_on=True)

        # Set the xlimit for the time plot.
        if np.size(Data.premidnight.filter) > 0:
            begin_plot_dt = Data.premidnight.localdates[-1]
            begin_plot_dt = datetime.datetime(
                begin_plot_dt.year,
                begin_plot_dt.month,
                begin_plot_dt.day,
                config.limits_time[0], 0, 0)
            end_plot_dt = begin_plot_dt + datetime.timedelta(
                hours=24 + config.limits_time[1] - config.limits_time[0])
        elif np.size(Data.aftermidnight.filter) > 0:
            end_plot_dt = Data.aftermidnight.localdates[-1]
            end_plot_dt = datetime.datetime(
                end_plot_dt.year,
                end_plot_dt.month,
                end_plot_dt.day,
                config.limits_time[1], 0, 0)
            begin_plot_dt = end_plot_dt - datetime.timedelta(
                hours=24 + config.limits_time[1] - config.limits_time[0])
        else:
            logger.warn('Cannot calculate plot limits')
            return None

        self.thegraph_time.set_xlim(begin_plot_dt, end_plot_dt)
        self.thegraph_time.set_ylim(config.limits_nsb)

        premidnight_label = str(Data.premidnight.label_dates).replace('[', '').replace(']', '')
        aftermidnight_label = str(Data.aftermidnight.label_dates).replace('[', '').replace(']', '')

        self.thegraph_time.text(0.00, 1.015,
                                config._device_shorttype + '-' + config._observatory_name + ' ' * 5 + 'Serial #' + str(
                                    Data.serial_number),
                                color='0.25', fontsize='small', fontname='monospace',
                                transform=self.thegraph_time.transAxes)

        if np.size(Data.Night) == 1:
            self.thegraph_time.text(0.75, 1.015, 'Moon: %d%s (%d%s)' % (
            Ephem.moon_phase, "%", Ephem.moon_maxelev * 180. / np.pi, "$^\mathbf{o}$"),
                                    color='black', fontsize='small', fontname='monospace',
                                    transform=self.thegraph_time.transAxes)

    def save_figure(self, output_filename):
        self.thefigure.savefig(output_filename, bbox_inches='tight', dpi=150)

    def show_figure(self):
        plt.show(self.thefigure)

    def close_figure(self):
        plt.close('all')


def save_stats_to_file(Night, NSBData, Ephem, config):
    '''
    Save statistics to file
    '''

    logger = logging.getLogger(__name__)

    Stat = NSBData.Statistics

    header0 = \
        '# Summary statistics for %s_%s\n' + \
        '# Description of columns (CSV file):\n' + \
        '# Col 1: Date\n' + \
        '# Col 2: Total measures\n' + \
        '# Col 3: Number of Best NSB measures\n' + \
        '# Col 4: Median of best N NSBs (mag/arcsec2)\n' + \
        '# Col 5: Err in the median of best N NSBs (mag/arcsec2)\n' + \
        '# Col 6: Number of terms of the low-freq fourier model\n' + \
        '# Col 7: Mean of Abs diff of NSBs data - fourier model (mag/arcsec2)\n' + \
        '# Col 8: Min Temp (C) between astronomical twilights\n' + \
        '# Col 9: Max Temp (C) between astronomical twilights\n\n'

    header = header0 % (config._device_shorttype, config._observatory_name)

    values = (Night, Stat.number,
              Stat.bests_number, Stat.bests_median,
              Stat.bests_err, Stat.model_nterm,
              Stat.data_model_abs_meandiff,
              Stat.min_temperature,
              Stat.max_temperature)

    formatted_data = "%s;%s;%s;%.4f;%.4f;%s;%.3f;.1f;%.1f\n" % values

    sfname = 'Statistics_%s_%s.dat' % (config._device_shorttype, config._observatory_name)

    statistics_filename = os.path.join(config.summary_data_directory, sfname)

    logger.info('Writing statistics file %s', statistics_filename)

    if not os.path.exists(statistics_filename):
        open(statistics_filename, 'w').close()

    # Read the content
    with open(statistics_filename, 'r') as thefile:
        stat_file_content = thefile.read()

    # If the file doesnt have a proper header, add it to the beginning
    def valid_line(line):
        if '#' in line:
            return False
        elif line.replace(' ', '') == '':
            return False
        else:
            return True

    if header not in stat_file_content:
        stat_file_content = [line for line in stat_file_content.split('\n') if valid_line(line)]
        stat_file_content = '\n'.join(stat_file_content)
        stat_file_content = header + stat_file_content
        with open(statistics_filename, 'w') as thefile:
            thefile.write(stat_file_content)

    # Remove any previous statistic for the given Night in the file
    if str(Night) in stat_file_content:
        stat_file_content = [line for line in stat_file_content.split('\n') if str(Night) not in line]
        stat_file_content = '\n'.join(stat_file_content)

        with open(statistics_filename, 'w') as thefile:
            thefile.write(stat_file_content)

    # Append to the end of the file
    with open(statistics_filename, 'a') as thefile:
        thefile.write(formatted_data)


def make_plot(config, input_filename=None, send_emails=False, write_stats=False):
    '''
    Main function (allows to execute the program
    from within python.
     - Extracts the NSB data from a given data file
     - Performs statistics
     - Save statistics to file
     - Create the plot
    '''
    logger = logging.getLogger(__name__)

    logger.info('Ploting photometer data ...')

    if input_filename is None:
        fname = "%s_%s.dat" % (config._device_shorttype, config._observatory_name)
        input_filename = os.path.join(config.current_data_directory, fname)

    # Define the observatory in ephem
    Ephem = obs.Ephemerids(config)

    # Get and process the data from input_filename
    nsbdata = SQMData(input_filename, Ephem, config=config)

    # Moon and twilight ephemerids.
    Ephem.calculate_moon_ephems(thedate=nsbdata.Night)
    Ephem.calculate_twilight(thedate=nsbdata.Night)

    # Calculate data statistics
    nsbdata.data_statistics(Ephem)

    # Write statiscs to file?
    if write_stats == True:
        save_stats_to_file(nsbdata.Night, nsbdata, Ephem, config=config)

    # Plot the data and save the resulting figure
    NSBPlot = Plot(nsbdata, Ephem, config=config)
    f10 = "%s_%s.png" % (config._device_shorttype, config._observatory_name)
    f1 = os.path.join(config.current_data_directory, f10)
    f20 = "%s_120000_%s-%s.png" % (str(nsbdata.Night).replace('-', ''),
                                   config._device_shorttype,
                                   config._observatory_name)
    f2 = os.path.join(config.daily_graph_directory, f20)
    output_filenames = [f1, f2]

    for output_filename in output_filenames:
        NSBPlot.save_figure(output_filename)

    # Close figure
    NSBPlot.close_figure()

    if send_emails:
        import pysqm.email
        night_label = str(datetime.date.today() - timedelta(days=1))
        pysqm.email.send_emails(night_label=night_label, Stat=nsbdata.Statistics)


# The following code allows to execute plot.py as a standalone program.

if __name__ == '__main__':
    # Exec the main program
    import pysqm.settings as settings

    InputArguments = settings.ArgParser()
    configfilename = InputArguments.get_config_filename()
    settings.GlobalConfig.read_config_file(configfilename)
    config = settings.GlobalConfig.config
    make_plot(input_filename=sys.argv[1], send_emails=False, write_stats=False)
