#
# Copyright 2018-2024 Universidad Complutense de Madrid
#
# This file is part of tesstractor
#
# SPDX-License-Identifier: GPL-3.0-or-later
# License-Filename: LICENSE.txt
#


import logging
import pkgutil
import datetime
import glob
import os.path

_logger = logging.getLogger(__name__)


# FIXME: simplify this
IDA_TMPL = {
    "TESS": "IDA-TESS-template.tpl",
    "TESS-R": "IDA-TESS-template.tpl",
    "TESSv2": "IDA-TESS-template.tpl",
    "SQM": "IDA-SQM-template.tpl",
    "SQM-LU": "IDA-SQM-template.tpl",
    "SQM-TEST": "IDA-SQM-template.tpl",
}


class TimeInterval:
    def __init__(self, min_val, max_val):
        self.min_val = min_val
        self.max_val = max_val

    def in_co(self, dt):

        if self.min_val <= dt < self.max_val:
            return True
        else:
            return False

    def in_oc(self, dt):
        if self.min_val < dt <= self.max_val:
            return True
        else:
            return False


class TimedDailyRotator:
    def __init__(self, when):
        self.when = when
        # self.interval = interval
        self.interval = datetime.timedelta(days=1.0)

    def in_interval(self, dt):
        ctime = dt.time()
        cdate = dt.date()

        lim = datetime.datetime.combine(cdate, self.when)
        if ctime < self.when:
            b = lim
            a = lim - self.interval
        else:
            a = lim
            b = lim + self.interval
        return TimeInterval(a, b)


def calc_filename(now, name):
    fname_tmpl = "{date:%Y%m%d_%H%M%S}_{name}.dat"
    return fname_tmpl.format(date=now, name=name)


def init_file(filename, insconf, locconf):
    model = insconf.model
    tmpl_path = IDA_TMPL[model]
    tmpl_b = pkgutil.get_data("tesstractor", tmpl_path)
    template_string = tmpl_b.decode("utf-8")
    with open(filename, "w") as fd:
        sus = template_string.format(instrument=insconf, location=locconf)
        # The data lines start after the header
        print(sus.rstrip("\n"), file=fd)


def startup(time_interval, name, dirname):

    candidates = []
    glob_pattern = "????????_??????_{}.dat".format(name)
    for f in glob.glob(os.path.join(dirname, glob_pattern)):
        # A RE would be more general?
        g = os.path.basename(f)
        r = g.split("_")
        rr = "_".join(r[:2])
        mm = datetime.datetime.strptime(rr, "%Y%m%d_%H%M%S")
        candidates.append((g, mm))
    candidates.sort(reverse=True)

    # print(candidates)
    # check most recent
    for cnd in candidates:
        fname, dt = cnd
        # TODO: we are checking all files here
        # but they are sorted, so less checks
        # are required
        if dt > time_interval.max_val:
            # This file is in the future, weird:
            continue

        if time_interval.in_co(dt):
            create = False
            filename = fname
            break
        else:
            # No candidates
            create = True
            filename = None
            break
    else:
        # No candidates
        create = True
        filename = None

    return create, filename


class FileSink:
    """Write measurements of a photometer to daily IDA files"""

    def __init__(self, dirname, devconf, location, local_tz):
        self.dirname = dirname
        self.devconf = devconf
        self.location = location
        self.local_tz = local_tz
        self.rot = TimedDailyRotator(when=datetime.time(hour=12, minute=0, second=0))
        self.valid_fname = None
        self.next_change = None

    def open(self):
        """Open the correct file, create a new one if it doesn't exist"""
        _logger.info("starting file writer of %s in %s", self.devconf.name, self.dirname)
        os.makedirs(self.dirname, exist_ok=True)

        ref_dt = datetime.datetime.now(self.local_tz).replace(tzinfo=None)
        _logger.debug("current local time, %s", ref_dt)

        valid_inter = self.rot.in_interval(ref_dt)
        self.next_change = valid_inter.max_val
        _logger.debug("interval of valid logs from %s upto %s", valid_inter.min_val, valid_inter.max_val)

        create, valid_fname = startup(valid_inter, self.devconf.name, self.dirname)
        if create:
            valid_fname = calc_filename(ref_dt, name=self.devconf.name)
            _logger.debug("valid file not found, create %s", valid_fname)
            init_file(os.path.join(self.dirname, valid_fname), self.devconf, self.location)
        else:
            _logger.debug("valid file is %s", valid_fname)
        self.valid_fname = valid_fname

    async def send(self, payload):
        """Write payload to the file"""
        # We are not going to write this to file anyway
        if payload["cmd"] == "id":
            return

        _logger.debug("got (w) payload %s", payload)
        # Add local time to payload
        payload = update_p(dict(payload))
        # Verify the file is correct before writing
        # if not, create a new one
        now_local_n = payload["tstamp_local"].replace(tzinfo=None)
        if now_local_n >= self.next_change:
            _logger.debug("read time is after scheduled time change, create new file")
            valid_inter = self.rot.in_interval(now_local_n)
            self.next_change = valid_inter.max_val
            self.valid_fname = calc_filename(now_local_n, name=self.devconf.name)
            init_file(os.path.join(self.dirname, self.valid_fname), self.devconf, self.location)
        write_to_file(payload, self.dirname, self.valid_fname)


def update_p(payload):
    """Update payload with tstamp_local"""
    payload["tstamp_local"] = payload["tstamp"].astimezone(payload["localtz"])
    return payload


def write_to_file(payload, dirname, filename):
    """Write payload to file"""
    payload["tstamp_str"] = payload["tstamp"].replace(tzinfo=None).isoformat("T", timespec="milliseconds")
    payload["tstamp_local_str"] = payload["tstamp_local"].replace(tzinfo=None).isoformat("T", timespec="milliseconds")
    line_tpl = (
        "{tstamp_str};{tstamp_local_str};{temp_ambient:.2f};"
        "{temp_sky:.2f};{freq_sensor:.3f};{magnitude:.2f};{zero_point}"
    )
    with open(os.path.join(dirname, filename), "a") as fd:
        if payload["cmd"] == "r":
            if "temp_ambient" not in payload:
                payload["temp_ambient"] = 0.0
            if "temp_sky" not in payload:
                payload["temp_sky"] = 0.0
            msg = line_tpl.format(**payload)
            print(msg, file=fd)
    return 0
