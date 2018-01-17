
import datetime
import ephem
import math


def define_ephem_observatory(config):
    """Define the Observatory in Pyephem"""
    obs = ephem.Observer()
    obs.lat = config._observatory_latitude * math.pi / 180.0
    obs.lon = config._observatory_longitude * math.pi / 180.0
    obs.elev = config._observatory_altitude
    return obs


def read_datetime():
    # Get UTC datetime from the computer.
    utc_dt = datetime.datetime.utcnow()
    return utc_dt


def local_datetime(utc_dt, local_timezone):
    # Get Local datetime from the computer, without daylight saving.
    return utc_dt + datetime.timedelta(hours=local_timezone)


def calculate_sun_altitude(obs, timeutc):
    # Calculate Sun altitude
    obs.date = ephem.date(timeutc)
    sun = ephem.Sun(obs)
    return sun.alt


def next_sunset(obs, observatory_horizon):
    # Next sunset calculation
    previous_horizon = obs.horizon
    obs.horizon = str(observatory_horizon)
    next_setting = obs.next_setting(ephem.Sun()).datetime()
    next_setting = next_setting.strftime("%Y-%m-%d %H:%M:%S")
    obs.horizon = previous_horizon
    return next_setting


def is_nighttime(obs, observatory_horizon):
    # Is nightime (sun below a given altitude)
    timeutc = read_datetime()
    if calculate_sun_altitude(obs, timeutc)* 180.0 / math.pi > observatory_horizon:
        return False
    else:
        return True


class Ephemerids(object):
    def __init__(self, config):
        self.Observatory = define_ephem_observatory(config)
        self.tz = config._local_timezone

    def ephem_date_to_datetime(self, ephem_date):
        # Convert ephem dates to datetime
        date_, time_ = str(ephem_date).split(' ')
        date_ = date_.split('/')
        time_ = time_.split(':')

        return (datetime.datetime(
            int(date_[0]), int(date_[1]), int(date_[2]),
            int(time_[0]), int(time_[1]), int(time_[2])))

    def end_of_the_day(self, thedate):
        newdate = thedate + datetime.timedelta(days=1)
        newdatetime = datetime.datetime(
            newdate.year,
            newdate.month,
            newdate.day, 0, 0, 0)
        newdatetime = newdatetime - datetime.timedelta(hours=self.tz)

        return newdatetime

    def calculate_moon_ephems(self, thedate):
        # Moon ephemerids
        self.Observatory.horizon = '0'
        self.Observatory.date = str(self.end_of_the_day(thedate))

        # Moon phase
        Moon = ephem.Moon()
        Moon.compute(self.Observatory)
        self.moon_phase = Moon.phase
        self.moon_maxelev = Moon.transit_alt

        try:
            float(self.moon_maxelev)
        except ValueError:
            # The moon has no culmination time for 1 day
            # per month, so there is no max altitude.
            # As a workaround, we use the previous day culmination.
            # The error should be small.

            # Set the previous day date
            thedate2 = thedate - datetime.timedelta(days=1)
            self.Observatory.date = str(self.end_of_the_day(thedate2))
            Moon2 = ephem.Moon()
            Moon2.compute(self.Observatory)
            self.moon_maxelev = Moon2.transit_alt

            # Recover the real date
            self.Observatory.date = str(self.end_of_the_day(thedate))

        # Moon rise and set
        self.moon_prev_rise = \
            self.ephem_date_to_datetime(self.Observatory.previous_rising(ephem.Moon()))
        self.moon_prev_set = \
            self.ephem_date_to_datetime(self.Observatory.previous_setting(ephem.Moon()))
        self.moon_next_rise = \
            self.ephem_date_to_datetime(self.Observatory.next_rising(ephem.Moon()))
        self.moon_next_set = \
            self.ephem_date_to_datetime(self.Observatory.next_setting(ephem.Moon()))

    def calculate_twilight(self, thedate, twilight=-18):
        '''
        Changing the horizon forces ephem to
        calculate different types of twilights:
        -6: civil,
        -12: nautical,
        -18: astronomical,
        '''
        self.Observatory.horizon = str(twilight)
        self.Observatory.date = str(self.end_of_the_day(thedate))

        self.twilight_prev_rise = self.ephem_date_to_datetime(
            self.Observatory.previous_rising(ephem.Sun(), use_center=True))
        self.twilight_prev_set = self.ephem_date_to_datetime(
            self.Observatory.previous_setting(ephem.Sun(), use_center=True))
        self.twilight_next_rise = self.ephem_date_to_datetime(
            self.Observatory.next_rising(ephem.Sun(), use_center=True))
        self.twilight_next_set = self.ephem_date_to_datetime(
            self.Observatory.next_setting(ephem.Sun(), use_center=True))
