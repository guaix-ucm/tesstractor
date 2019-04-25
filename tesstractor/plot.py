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


def do_plots_on_dir(dirname):
    import pathlib

    logger = logging.getLogger(__name__)

    data_files = []
    for f in os.listdir(dirname):
        if f.endswith('.dat'):
            data_files.append(f)

    for filed in data_files:
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
            pathlib.Path(filep_f).touch()
        else:
            logger.debug('%s plot older than data, nothing to do', filep)


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


if __name__ == '__main__':
    main()
