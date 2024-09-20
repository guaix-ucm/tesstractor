#
# Copyright 2018-2024 Universidad Complutense de Madrid
#
# This file is part of tesstractor
#
# SPDX-License-Identifier: GPL-3.0-or-later
# License-Filename: LICENSE.txt
#


import re
import argparse

# from astropy.io import registry
import astropy.table
import astropy.io.ascii
import astropy.units as u


def meta_as_type(key, conv):
    """Convert entries in file header"""
    def converter(value, meta):
        meta[key] = conv(value.strip())

    return converter


def position_converter(value, meta):
    """Convert longitude, latitude, height in file header"""
    vals = [float(val) for val in value.split(',')]

    if len(vals) < 3:
        raise ValueError('"longitude, latitude, height" is needed')

    meta['lon'] = vals[0] * u.deg
    meta['lat'] = vals[1] * u.deg
    meta['height'] = vals[2] * u.m


def remove_quotes(value):
    value = value.strip('\"').strip("\'")
    return value


# Entries in the header that are read
_header_entries = {
    'device_type': meta_as_type('device_type', str),
    'local_timezone': meta_as_type('timezone', remove_quotes),
    'instrument_id': meta_as_type('instrument_id', str),
    'data_supplier': meta_as_type('data_supplier', str),
    'location_name': meta_as_type('location_name', str),
    'position': position_converter,
}


class IDAHeader(astropy.io.ascii.basic.BasicHeader):
    """Read the header of a IDA file"""

    def process_lines(self, lines):
        re_comment = re.compile(self.comment)
        for line in lines:
            line = line.strip()
            if not line:
                continue
            match = re_comment.match(line)
            if match:
                out = line[match.end():]
                if out:
                    yield out
            else:
                # Stop iterating on first failed match for a non-blank line
                return

    def update_meta(self, lines, meta):
        # super().update_meta(lines, meta)
        sub_header = list(self.process_lines(lines))

        meta_t = meta['table']
        key_val_re = re.compile(r"""
                        \s* # Skip whitespace
                        (?P<key>.*?):(?P<value>.*$)
                        """, re.VERBOSE)
        re_key = re.compile(key_val_re)
        for lih in sub_header:
            match = re_key.match(lih)
            if match:
                key = match.group("key")
                canon_key = '_'.join(w.lower() for w in key.split(" "))
                value = match.group("value")
                if canon_key in _header_entries:
                    func = _header_entries[canon_key]
                    func(value, meta_t)
            else:
                pass

    def get_cols(self, lines):

        start_line = 0

        for i, line in enumerate(self.process_lines(lines)):
            if i == start_line:
                break
            else:  # No header line matching
                raise ValueError('No header line found in table')

        # self.names = next(self.splitter([line]))
        # This could come from the last but one line in the header
        self.names = ['time_utc', 'time_local', 'temp', 'sky_temp', 'freq', 'mag', 'zp']
        self._set_cols_from_names()


class IDAData(astropy.io.ascii.BaseData):
    def process_lines(self, lines):
        lc = 0
        MAX_LC = 35
        for line in lines:
            lc += 1
            if lc > MAX_LC:
                yield line


class IDAReader(astropy.io.ascii.BaseReader):
    """IDA table reader"""
    _format_name = 'IDA'
    _description = 'IDA table format'

    _io_registry_can_write = False

    def __init__(self):
        super().__init__()

        self.header = IDAHeader()
        self.data = IDAData()
        self.data.header = self.header
        self.header.data = self.data
        self.data.splitter.delimiter = ';'

    def write(self, table=None):
        raise NotImplementedError


def read_file(filed_f):

    table_obj = astropy.table.Table.read(
        filed_f, format='ascii.IDA'
    )
    return table_obj


def print_tab(table_obj):

    print(table_obj.colnames)
    print(table_obj.meta)
    print(table_obj.info)
    return table_obj


def main(args=None):
    # Parse CLI
    parser = argparse.ArgumentParser()
    parser.add_argument('path')
    pargs = parser.parse_args(args=args)

    t1 = read_file(pargs.path)
    print_tab(t1)


if __name__ == '__main__':
    main()
