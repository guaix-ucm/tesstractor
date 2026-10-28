[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.2563065.svg)](https://doi.org/10.5281/zenodo.2563065)

# TESStractor #

Tesstractor is a software designed to read data from
TESS photometers (http://tess.stars4all.eu/).

This software reads data also from Unihedron SQM-LU photometers.

The measurements can be:

- written to daily files in the IDA format, following the community
  standard data format for skyglow observations (NSBM)
- sent via MQTT to the STARS4ALL server

## Installation ##

Tesstractor requires Python 3.11 or later. Install it from PyPI, preferably
in a virtual environment:

    $ python3 -m venv venv
    $ venv/bin/pip install tesstractor

In Fedora, RPM packages are available in
[COPR](https://copr.fedorainfracloud.org/coprs/sergiopr/tesstractor/). They
install the systemd service and the configuration in `/etc/tesstractor/config.ini`:

    $ sudo dnf copr enable sergiopr/tesstractor
    $ sudo dnf install tesstractor

## Usage ##

Generate a template configuration file and edit it:

    $ tesstractor --generate-config > config.ini

Enable the `[photometer_*]` sections of your devices (`enabled: True`), fill
the `[location]` section and enable the outputs, `[file]` and/or `[mqtt]`.
Then run:

    $ tesstractor -c config.ini

If a photometer is enabled but no output is, the photometer is read but the
measurements are not stored.

Tesstractor runs until it receives SIGTERM or SIGINT (Ctrl-C); the pending
measurements are averaged and written before exiting. If a photometer fails
or is disconnected, it exits with code 1 and logs the cause.

Plots of the data files (sky brightness, Sun and Moon) are created with:

    $ tesstractor-plot <file.dat or directory>

With a directory, only the files newer than their plots are plotted.

## Configuration ##

The configuration file has several sections. Sections starting with
`photometer`, `file` or `mqtt` can be repeated with different suffixes (for
example `[photometer_sqm]` and `[photometer_tess]`); every enabled photometer
is read and sent to every enabled output. Any section is enabled unless it
has `enabled: False`.

### Photometers ###

| Option | Default | Description |
|---|---|---|
| `model` | `SQM-TEST` | `SQM-LU`, `TESS-R` (also `TESS`, `TESS-U`), `TESSv2`, or `SQM-TEST` (simulated) |
| `name` | | Name of the photometer, used in file names and MQTT (`TESSv2` reports its own) |
| `port` | `/dev/ttyUSB0` | Serial port, see [Serial ports](#serial-ports) |
| `baudrate` | 115200 (SQM), 9600 (TESS) | |
| `timeout` | 2.0 (SQM), 1.0 (TESS) | Seconds to wait for a line from the photometer |
| `tsample` | 1.0 | Seconds between readings |
| `nsamples` | 0 | Readings averaged before sending them to the outputs; 0 or 1, no averaging |
| `zero_point` | 20.0 | Zero point of TESS photometers (the SQM and `TESSv2` report their own) |
| `mac` | | MAC address of the TESS, for the file header and the MQTT registration |
| `filter`, `fov`, `azimuth`, `altitude`, `cover_offset` | | Description of the instrument for the file header |

The photometers do not report their filter, field of view, pointing or cover
offset. If these options are not given, the fields of the file header are left
empty, as required by the NSBM standard. For example, for an SQM-LU pointing
to the zenith:

    [photometer_sqm]
    model: SQM-LU
    name: sqm-2747
    port: /dev/serial/by-id/usb-FTDI_MM232R_USB_MODULE_FTGHU9Z5-if00-port0
    filter: HOYA CM-500
    fov: 20
    azimuth: 0
    altitude: 90
    cover_offset: -0.11

### Location ###

The values of the `[location]` section are written in the header of the data
files: `contact_name`, `organization`, `locality`, `province`, `country`,
`site`, `latitude` and `longitude` (decimal degrees, negative to the South and
West), `elevation` (meters), `timezone` (for example `Europe/Madrid`) and
`timesync`.

### Files ###

| Option | Default | Description |
|---|---|---|
| `dirname` | `/var/lib/tesstractor` | Directory of the data files, created if needed |
| `interval` | 300.0 | Seconds to average the measurements; 0 writes every measurement as given by the photometer |

There is one file per photometer and day, starting at 12:00 local time. The
files follow the NSBM standard: `;` separated fields, UTC and local time in
each line, and empty fields for the values not provided by the photometer
(for example, the temperatures of a TESS without temperature sensors). The
averaged files contain the median of the measurements in each interval.

### MQTT ###

| Option | Default | Description |
|---|---|---|
| `hostname` | | MQTT server, `astrix.fis.ucm.es` for STARS4ALL |
| `port` | 1883 | |
| `tls` | False | Use TLS |
| `username`, `password` | | Credentials |
| `register_topic` | | Topic of the registration messages, `STARS4ALL/register` |
| `publish_topic` | | Topic of the measurements, `STARS4ALL/{name}/reading` |
| `interval` | 60.0 | Seconds to average the measurements; 0 sends every measurement |
| `reconnect_interval` | 30.0 | Seconds between attempts to connect to the server |

The measurements are queued while the server is not available. To obtain
the credentials for the STARS4ALL server, contact
[Jaime Zamorano](mailto:jzamorano@fis.ucm.es).

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

## Running as a service ##

`extras/tesstractor.service` is a systemd unit that runs
`tesstractor -c /etc/tesstractor/config.ini` and restarts it on failure.
Adjust the paths, copy it to `/etc/systemd/system/` and enable it. If
tesstractor is installed in a virtual environment, use the `tesstractor` of
the environment in `ExecStart`, for example
`ExecStart=/path/to/venv/bin/tesstractor -c /path/to/config.ini`.

    $ sudo systemctl enable --now tesstractor.service

`extras/tesstractor-plot.service` and `extras/tesstractor-plot.timer` update
the plots of the data files in `/var/lib/tesstractor` every 15 minutes:

    $ sudo systemctl enable --now tesstractor-plot.timer

`extras/81-sqm.rules` is a udev rule that starts the service when the USB
serial adapter of a photometer is connected. Many devices use the same FTDI
chip, so edit it with the serial number of your adapter before copying it to
`/etc/udev/rules.d/`.

The RPM packages install the three systemd units; the udev rule is in the
documentation directory.

## Licensing ##

Tesstractor is distributed under GNU GPL, either version 3 of the License,
or (at your option) any later version. See the file LICENSE.txt for details.

## Authors ##

Webpage: https://github.com/guaix-ucm/tesstractor
Maintainer: sergiopr@fis.ucm.es
