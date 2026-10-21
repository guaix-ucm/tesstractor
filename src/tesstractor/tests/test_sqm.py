import math

import pytest

from ..sqm import MEASURE_RE, META_RE, CALIB_RE, SQMLU, SQMTest, sensor_frequency
from .fakes import FakeSerial

IX = b"i,00000004,00000006,00000029,00002747\r\n"
CX = b"c,00000019.89m,0000300.000s, 021.9C,00000008.71m, 020.9C\r\n"
RX = b"r, 17.54m,0000000009Hz,0000053495c,0000000.116s, 021.2C\r\n"
# Dark sky, the frequency in Hz is 0
RX_DARK = b"r, 21.30m,0000000000Hz,0001521600c,0000003.302s, 012.0C\r\n"


@pytest.mark.parametrize(
    "msg",
    [
        b"r, 15.79m,0000000042Hz,0000011099c,0000000.024s, 026.7C\r\n",
        b"r, 15.61m,0000000049Hz,0000009384c,0000000.020s,-000.0C\r\n",
        b"r, 06.53m,0000211313Hz,0000000000c,0000000.000s, 027.0C\r\n",
    ],
)
def test_data_re1(msg):
    matches = MEASURE_RE.match(msg)
    assert matches


@pytest.mark.parametrize("msg", [b"i,00000004,00000003,00000023,00002142\r\n"])
def test_metadata_re1(msg):
    matches = META_RE.match(msg)
    assert matches


@pytest.mark.parametrize("msg", [b"c,00000019.84m,0000151.517s, 022.2C,00000008.71m, 023.2C\r\n"])
def test_calibration_re1(msg):
    matches = CALIB_RE.match(msg)
    assert matches


@pytest.mark.parametrize(
    "msg, freq",
    [
        (RX, 460800 / 53495),
        (RX_DARK, 460800 / 1521600),
        # Bright, no period counts
        (b"r, 06.53m,0000211313Hz,0000000000c,0000000.000s, 027.0C\r\n", 211313),
    ],
)
def test_sensor_frequency(msg, freq):
    assert sensor_frequency(MEASURE_RE.match(msg)) == pytest.approx(freq)


def test_frequency_matches_device_magnitude():
    # Real readout of SQM-LU 2747
    freq = sensor_frequency(MEASURE_RE.match(RX))
    assert 19.89 - 2.5 * math.log10(freq) == pytest.approx(17.54, abs=0.02)


def test_sqmlu_start_connection():
    conn = FakeSerial({b"ix": [IX], b"cx": [CX], b"rx": [RX]})
    dev = SQMLU(conn, "sqm1")
    dev.cmd_wait = 0
    dev.start_connection()
    assert dev.serial_number == 2747
    assert dev.calibration == 19.89
    conf = dev.static_conf()
    assert conf.serial_number == 2747
    assert conf.rx_readout == RX.strip()


def test_sqmlu_malformed_answer_retries():
    # A corrupt line, then a valid one. The command must be sent again
    conn = FakeSerial({b"ix": [IX], b"cx": [CX], b"rx": [b"r, 17.5garbage\r\n", RX]})
    dev = SQMLU(conn, "sqm1")
    dev.cmd_wait = 0
    data = dev.read_data(tries=3)
    assert data is not None
    assert data["magnitude"] == 17.54
    assert conn.written == [b"rx", b"rx"]


def test_sqmlu_reset_reopens_port():
    conn = FakeSerial({b"ix": [IX], b"cx": [CX], b"rx": [b"\r\n", RX]})
    dev = SQMLU(conn, "sqm1")
    dev.cmd_wait = 0
    conn.close()
    dev.reset_device()
    assert conn.is_open
    assert dev.read_data(tries=3)["magnitude"] == 17.54


def test_sqmlu_no_answer():
    conn = FakeSerial({b"ix": [b""], b"cx": [CX], b"rx": [b""]})
    dev = SQMLU(conn, "sqm1")
    dev.cmd_wait = 0
    assert dev.read_data(tries=2) is None
    with pytest.raises(ValueError):
        dev.read_metadata(tries=2)


def test_sqmtest():
    dev = SQMTest()
    dev.start_connection()
    data = dev.read_data()
    assert data["valid"]
