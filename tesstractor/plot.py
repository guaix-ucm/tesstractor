#
# Copyright 2018-2019 Universidad Complutense de Madrid
#
# This file is part of tesstractor
#
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSE.txt
#


import os.path
import logging
import argparse
from datetime import datetime, timedelta

import numpy as np
import pytz
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
from astropy.coordinates import get_sun, get_moon
from astropy.coordinates import EarthLocation
from astropy.time import Time
import astropy.table
import astropy.units as u
import astroplan

# Import IDA format reader
import tesstractor.reader

# Style for saving into PNG
my_style1 = {
   "figure.figsize": (9, 7),
    "savefig.dpi": 200,
    "axes.labelsize": 14
}

def plot_sun(ax, site, base_time):
    # SUN
    tsmin, tsmax = ax.get_xlim()

    tmin = mdates.num2date(tsmin, tz=site.timezone)
    tmax = mdates.num2date(tsmax, tz=site.timezone)

    # Time of lower alt of the sun
    sun_a = site.target_meridian_antitransit_time(base_time, get_sun(base_time))
    sun_a_dt = site.astropy_time_to_datetime(sun_a)
    ax.axvline(sun_a_dt, color='k', ls='--', lw=2, alpha=0.5, clip_on=True)

    tmin_utc = tmin.astimezone(pytz.utc)
    tmax_utc = tmax.astimezone(pytz.utc)

    # Calc Sun's altitude every 15m
    ctimes_dt = []
    newtime = tmin_utc
    while newtime < tmax_utc:
        ctimes_dt.append(newtime)
        newtime += timedelta(minutes=15)

    times = Time(ctimes_dt)
    sun_altaz = site.altaz(times, get_sun(times))
    min_alt = min(sun_altaz.alt)
    max_alt = max(sun_altaz.alt)

    # print('min alt:', min_alt.deg, 'max alt:', max_alt.deg)

    there_is_day = (max_alt > 0)
    there_is_night = (min_alt < 0)

    if there_is_day and there_is_night:
        # print('n & d')
        sun_e = site.sun_set_time(base_time)
        sun_m = site.sun_rise_time(base_time)
        sun_e_dt = site.astropy_time_to_datetime(sun_e)
        sun_m_dt = site.astropy_time_to_datetime(sun_m)

        ax.axvline(sun_e_dt, color='g', ls='--', lw=2, alpha=0.5, clip_on=True)
        ax.axvline(sun_m_dt, color='r', ls='--', lw=2, alpha=0.5, clip_on=True)

        # Aprox, the same hour, but tomorrow
        sun_en_dt = sun_e_dt + timedelta(days=1)
        sun_mp_dt = sun_m_dt - timedelta(days=1)
        ax.axvspan(sun_mp_dt, sun_e_dt, alpha=0.1)
        ax.axvspan(sun_m_dt, sun_en_dt, alpha=0.1)
        # print(sun_mp_dt, sun_e_dt)

        tw_lim = -18 * u.deg
        if min_alt < tw_lim:
            # plot astronomical tw
            sun_e = site.sun_set_time(base_time, horizon=tw_lim)
            sun_m = site.sun_rise_time(base_time, horizon=tw_lim)
            sun_e_dt = site.astropy_time_to_datetime(sun_e)
            sun_m_dt = site.astropy_time_to_datetime(sun_m)

            ax.axvline(sun_e_dt, color='g', ls='--', lw=2, alpha=0.5, clip_on=True)
            ax.axvline(sun_m_dt, color='r', ls='--', lw=2, alpha=0.5, clip_on=True)
    else:
        if there_is_day:
            print('The sun is over the horizon all day')
            rect = mpatches.Rectangle(
                (0, 0), width=1, height=1,
                transform=ax.transAxes, color='blue', alpha=0.1)
            ax.add_patch(rect)
        else:
            print('The sun is under the horizon all night')
    # Reset
    ax.set_xlim((tmin, tmax))


def plot_moon(ax, site, base_time):
    # MOON
    tsmin, tsmax = ax.get_xlim()
    tmin = mdates.num2date(tsmin, tz=site.timezone)
    tmax = mdates.num2date(tsmax, tz=site.timezone)
    tmin_utc = tmin.astimezone(pytz.utc)
    tmax_utc = tmax.astimezone(pytz.utc)

    # Calc Moon's altitude every 15m
    ctimes_dt = []
    newtime = tmin_utc
    while newtime < tmax_utc:
        ctimes_dt.append(newtime)
        newtime += timedelta(minutes=15)

    times = Time(ctimes_dt)
    moon_altaz = site.altaz(times, get_moon(times))
    min_alt = min(moon_altaz.alt)
    max_alt = max(moon_altaz.alt)

    print('min alt:', min_alt.deg, 'max alt:', max_alt.deg)
    ax.set_ylim([0, 90])
    ax.set_ylabel('Moon altitude (deg)')
    ax.plot(ctimes_dt, moon_altaz.alt, ls='-.', lw=1, color='black')


def gen_plot(ax, tval, magval, site, ref_day, meta):

    hours = mdates.HourLocator(interval=2)
    mins = mdates.MinuteLocator(byminute=[0, 30])
    hoursfmt = mdates.DateFormatter("%H", tz=site.timezone)
    next_day = ref_day + timedelta(days=1)
    base_time = Time(ref_day.astimezone(pytz.utc))
    if len(tval) > 0:
        ax.plot(tval, magval, '+')
    else:
        t1 = ref_day
        t2 = ref_day + timedelta(seconds=7200)
        ax.set_xlim(t1, t2)
    utco = ref_day.strftime("%z")
    day1 = ref_day.strftime("%Y-%m-%d")
    day2 = next_day.strftime("%Y-%m-%d")
    title_label1 = 'device: {device_type} {instrument_id}'.format(**meta)
    title_label2 = 'date: {}/{}'.format(day1, day2)
    title_label = '{:^15}   {:^15}'.format(title_label1, title_label2)
    ax.set_title(title_label)
    ax.set_xlabel('Local time (UTC {})'.format(utco))
    ax.set_ylabel('sky brightness (mag / arcsec^2)')
    # SUN
    plot_sun(ax, site, base_time)
    # MOON
    ax2 = ax.twinx()
    plot_moon(ax2, site, base_time)

    ax.xaxis.set_major_locator(hours)
    ax.xaxis.set_major_formatter(hoursfmt)
    ax.xaxis.set_minor_locator(mins)
    ax.grid(True)
    ax.format_xdata = mdates.DateFormatter("%H:%M:%S", tz=site.timezone)


def do_plots_on_dir(dirname):
    logger = logging.getLogger(__name__)

    data_files = []
    for f in os.listdir(dirname):
        if f.endswith('.dat'):
            data_files.append(f)

    for filed in sorted(data_files):
        fname, ext = os.path.splitext(filed)
        filep = fname + '.png'
        filed_f = os.path.join(dirname, filed)
        filep_f = os.path.join(dirname, filep)
        tfiled = os.path.getmtime(filed_f)
        try:
            tfilep = os.path.getmtime(filep_f)
        except FileNotFoundError:
            tfilep = 0

        if tfiled > tfilep:
            logger.debug('%s data older than plot, update', filed)

            plot_file(filed_f, filep_f)
        else:
            logger.debug('%s plot older than data, nothing to do', filep)


def do_plots_on_file(filename):
    fname, ext = os.path.splitext(filename)
    filep = fname + '.png'
    plot_file(filename, filep)


def plot_file(filed_f, filep_f):
    table_obj = astropy.table.Table.read(
        filed_f, format='ascii.IDA')

    with plt.style.context(my_style1):
        fig = plot_table(table_obj)
        fig.savefig(filep_f)
        plt.close(fig)


def plot_table(tab):
    min_mag = 12

    lat = tab.meta['lat']
    lon = tab.meta['lon']
    height = tab.meta['height']
    timezone = tab.meta['timezone']
    location = EarthLocation(lat=lat, lon=lon, height=height)
    site = astroplan.Observer(location=location, name=tab.meta['location_name'], timezone=timezone)

    t1 = np.array([pytz.utc.localize(datetime.fromisoformat(value)) for value in tab['time_utc']])
    tval_local = np.array([tutc.astimezone(site.timezone) for tutc in t1])
    magval_local = tab['mag']

    # Filter mag values above 12
    mask_5 = magval_local > min_mag
    tval_local_f = tval_local[mask_5]
    magval_local = magval_local[mask_5]

    if len(tval_local_f) > 0:
        ref_time = tval_local_f[0]
    elif len(tval_local) > 0:
        ref_time = tval_local[0]
    else:
        # Empty file
        return None

    ref_day = datetime(
        year=ref_time.year,
        month=ref_time.month,
        day=ref_time.day,
        hour=23,
        minute=55,
        second=0
    )
    ref_day = site.timezone.localize(ref_day)
    fig = plt.figure()
    ax = fig.add_subplot()
    gen_plot(ax, tval_local_f, magval_local, site, ref_day, tab.meta)
    return fig


def main(args=None):
    # Parse CLI
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRTICAL', 'NOTSET']
                        )
    parser.add_argument('path')
    pargs = parser.parse_args(args=args)

    loglevel = getattr(logging, pargs.log.upper())

    logging.basicConfig(level=loglevel)
    logger = logging.getLogger(__name__)
    logger.info('tesstractor-plot, starting')

    if os.path.isdir(pargs.path):
        logger.debug('path is dir')
        do_plots_on_dir(pargs.path)
    else:
        logger.debug('path is file')
        do_plots_on_file(pargs.path)


if __name__ == '__main__':
    main()
