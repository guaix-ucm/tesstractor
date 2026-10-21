[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.2563065.svg)](https://doi.org/10.5281/zenodo.2563065)

# TESStractor #

Tesstractor is a software designed to read data from
TESS photometers (http://tess.stars4all.eu/).

This software reads data also from Unihedron SQM-LU photometers.

## Serial ports ##

The `/dev/ttyUSB*` name of a photometer depends on the order in which the
devices are connected, and it may change after disconnecting a device or
rebooting. Use the stable names in `/dev/serial/by-id/` in the `port` option
of the configuration, they include the serial number of the USB adapter:

    $ ls -l /dev/serial/by-id/
    usb-FTDI_FT232R_USB_UART_AH034K0K-if00-port0 -> ../../ttyUSB1
    usb-FTDI_MM232R_USB_MODULE_FTGHU9Z5-if00-port0 -> ../../ttyUSB0

    [photometer_sqm]
    model: SQM-LU
    port: /dev/serial/by-id/usb-FTDI_MM232R_USB_MODULE_FTGHU9Z5-if00-port0

If a photometer is disconnected, tesstractor exits with an error; with the
systemd service in `extras/` it is restarted after 30 seconds.

## Licensing ##

Tesstractor is distributed under GNU GPL, either version 3 of the License,
or (at your option) any later version. See the file LICENSE.txt for details.

## Authors ##

Webpage: https://github.com/guaix-ucm/tesstractor
Maintainer: sergiopr@fis.ucm.es
