import math

import pytest

from ..tess import MEASURE_RE, TessR, TessV2
from ..workers import avg_device_buffer
from .fakes import StreamSerial

LINE_H = b"<fH 04606><tA +2987><tO +2481><mZ -0000>\r\n"
LINE_M = b"<fm 00123><tA +2987><tO +2481>\r\n"


@pytest.mark.parametrize("msg", [LINE_H, LINE_M, b"<fm-00000>\r\n"])
def test_measure_re(msg):
    assert MEASURE_RE.match(msg)


@pytest.mark.parametrize("msg, freq", [(LINE_H, 4606.0), (LINE_M, 0.123)])
def test_tessr_process_msg(msg, freq):
    dev = TessR(StreamSerial([]), "tess1")
    dev.calibration = 20.5
    res = dev.process_msg(MEASURE_RE.match(msg))
    assert res["valid"]
    assert res["freq_sensor"] == pytest.approx(freq)
    assert res["magnitude"] == pytest.approx(20.5 - 2.5 * math.log10(freq))
    assert res["temp_ambient"] == 29.87
    assert res["temp_sky"] == 24.81
    assert res["zero_point"] == 20.5
    assert res["tstamp"].tzinfo is not None


def test_tessr_average_keeps_magnitude():
    dev = TessR(StreamSerial([]), "tess1")
    dev.calibration = 20.5
    res = dev.process_msg(MEASURE_RE.match(LINE_H))
    avg = avg_device_buffer([res, res])
    assert avg["magnitude"] == pytest.approx(res["magnitude"])


def test_tessr_read_data_skips_malformed():
    conn = StreamSerial([b"garbage\r\n", LINE_H])
    dev = TessR(conn, "tess1")
    res = dev.read_data(tries=3)
    assert res["freq_sensor"] == 4606.0


def test_tessr_read_data_none():
    dev = TessR(StreamSerial([b"garbage\r\n"] * 3), "tess1")
    assert dev.read_data(tries=3) is None


def test_tessv2():
    msg = b'{"udp":83471,"rev":2,"name":"stars605","freq":13.38,"mag":17.52,"tamb":30.39,"tsky":29.23,"ZP":20.34}\r\n'
    dev = TessV2(StreamSerial([b"WIFI connecting\r\n", msg]), "stars605")
    dev.calibration = 20.34
    assert dev.read_data() is None
    res = dev.read_data()
    assert res["freq_sensor"] == 13.38
    assert res["temp_sky"] == 29.23


def test_tessv2_missing_values():
    dev = TessV2(StreamSerial([b'{"rev":2,"freq":13.38,"ZP":20.0}\r\n']), "stars605")
    dev.calibration = 20.0
    assert dev.read_data() is None
