# Changes #

## 0.8.0 (unreleased) ##

### Requirements ###

- Python 3.11 or later (3.11 to 3.14 are tested).
- New dependency: `aiomqtt`. `paho-mqtt` 2 or later.

### Fixed: data ###

- SQM: measurements under dark skies were discarded. The SQM reports the
  frequency as an integer number of Hz, 0 under dark skies, and the averages
  were marked as invalid. The frequency is now computed from the period
  counts.
- The averaged magnitude was recomputed from the frequency, losing the
  corrections made by the SQM firmware (about 0.06 mag under dark skies).
  The averages now use the median of the magnitudes given by the photometer.
- TESS-R photometers could not be used: the configuration did not create
  the device, measurements lacked the time and the zero point, and the
  frequency was in mHz.
- TESSv2 messages without frequency or magnitude made tesstractor fail.
- The first measurement of each data file was appended to the
  `# END OF HEADER` line.
- Latitude and longitude were swapped in the sample configuration and in
  the reader of the data files. **Check the `[location]` section of your
  configuration**: latitude first, negative to the South and West.

### Fixed: reliability ###

- A corrupted line from an SQM closed the serial port and stopped the
  program. Lines are retried, sending the command again.
- With a wrong baud rate or serial port, tesstractor could hang without
  logging anything and ignoring SIGTERM. It now exits with an error.
- Lines sent in pieces by some TESS photometers were discarded.
- Measurements pending to be averaged were lost on exit.
- If the MQTT server was not available on startup, MQTT was disabled until
  the next restart. tesstractor now reconnects, sends the registration again
  and queues the measurements meanwhile.
- If an output failed, its queue grew without limit. Now any failure stops
  tesstractor with exit code 1, and the error message names the photometer.
- The daily rotation of files used the time zone of the computer instead of
  the one in the configuration.
- `tesstractor-plot` failed with astropy 7, took minutes with files of a
  single measurement, and stopped at the first file that could not be
  plotted (for example, a new file with only the header).

### New ###

- All the enabled photometers are read, not only the first one.
- `interval: 0` in a `[file]` or `[mqtt]` section sends every measurement as
  given by the photometer, without averaging.
- MQTT options `port`, `tls` and `reconnect_interval`.
- Photometer options `filter`, `fov`, `azimuth`, `altitude` and
  `cover_offset`, for the file header.

### Changes in the data files ###

The files follow the community standard data format for skyglow
observations (NSBM):

- Values not provided by the photometer are left empty instead of `0.00`,
  for example the sky temperature of an SQM or the temperatures of a TESS
  without temperature sensors.
- Header values that were placeholders (filter `b`, field of view `20`,
  cover offset `-0.11`, a fake TESS MAC address, firmware `0`) are left
  empty unless they are set in the configuration. Set them in the
  photometer section if your files need them.
- The measurement direction is the zenith angle and the azimuth, in that
  order. Previously it was written as `0.0, 90.0 - 0.0`.
- Position with four decimals for latitude and longitude, and the elevation
  without decimals.
- The number of fields per line is 7.
- The frequency is written with three decimals.
- The SQM readouts in the header are written as text, not as `b'...'`.

### Other ###

- The data files (templates, sample configuration) were missing in packages
  built from a tarball instead of a git checkout.
- `tesstractor-plot` works without network access.
- RPM packages are built in COPR for each release, with Packit. They
  include the systemd service and the configuration in `/etc/tesstractor`.
- The threads were replaced by asyncio tasks.
- The systemd unit waits for the network and restarts tesstractor on
  failure.
- The README documents the configuration and recommends the stable serial
  port names in `/dev/serial/by-id/`.
