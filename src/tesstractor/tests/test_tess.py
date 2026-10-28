import math

import pytest

from ..tess import MEASURE_RE, UNKNOWN_MAC, TessR, TessV2
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


# Line of a TESSv2 without temperature sensors
LINE_V2 = (
    b'{"udp":40, "rev":2, "name":"stars111", "freq":75.14, "mag":15.44, "tamb":0.00, "tsky":0.00,'
    b' "wdBm":0, "hash":"988", "ain":364, "ZP":20.13}\r\n'
)
LINE_V2_TEMPS = (
    b'{"udp":83471,"rev":2,"name":"stars605","freq":13.38,"mag":17.52,"tamb":30.39,"tsky":29.23,"ZP":20.34}\r\n'
)


def test_tessv2_start_connection():
    conn = StreamSerial([b"\xfcets Jul 29 2019 12:21:46\r\n", b"45\r\n", b"\r\n", LINE_V2])
    dev = TessV2(conn)
    dev.start_connection()
    assert dev.name == "stars111"
    assert dev.serial_number == "stars111"
    assert dev.calibration == 20.13
    assert dev.static_conf().zero_point == 20.13


def test_tessv2_start_connection_no_data():
    dev = TessV2(StreamSerial([b"45\r\n", b"\r\n", b"WIFI connecting\r\n"]))
    with pytest.raises(ValueError, match="no valid data"):
        dev.start_connection(tries=5)


def test_tessv2_start_connection_conf_differs(caplog):
    dev = TessV2(StreamSerial([LINE_V2]), "other", 20.0)
    dev.start_connection()
    assert dev.name == "stars111"
    assert dev.calibration == 20.13
    assert "name in the configuration is other" in caplog.text
    assert "zero_point in the configuration is 20.0" in caplog.text


def test_tessv2_read_data():
    dev = TessV2(StreamSerial([LINE_V2, b"\r\n", b"50\r\n", LINE_V2]))
    dev.start_connection()
    res = dev.read_data(tries=3)
    assert res["valid"]
    assert res["name"] == "stars111"
    assert res["freq_sensor"] == 75.14
    assert res["magnitude"] == 15.44
    assert res["zero_point"] == 20.13
    assert res["protocol_revision"] == 2
    assert res["tstamp"].tzinfo is not None
    # 0.00 in both temperatures, there are no sensors
    assert "temp_ambient" not in res
    assert "temp_sky" not in res


def test_tessv2_read_data_none():
    dev = TessV2(StreamSerial([b"\r\n", b"50\r\n", b"\r\n"]))
    assert dev.read_data(tries=3) is None


def test_tessv2_temperatures():
    dev = TessV2(StreamSerial([LINE_V2_TEMPS]))
    dev.calibration = 20.34
    res = dev.read_data()
    assert res["temp_ambient"] == 30.39
    assert res["temp_sky"] == 29.23


def test_tessv2_missing_values():
    dev = TessV2(StreamSerial([b'{"rev":2,"freq":13.38,"ZP":20.0}\r\n']), "stars605")
    dev.calibration = 20.0
    assert dev.read_data() is None


def test_tessv2_zero_freq():
    dev = TessV2(StreamSerial([LINE_V2.replace(b'"freq":75.14', b'"freq":0.00')]))
    dev.calibration = 20.13
    assert not dev.read_data()["valid"]


def test_tessv2_zero_point_changes(caplog):
    dev = TessV2(StreamSerial([LINE_V2, LINE_V2.replace(b"20.13", b"20.20"), LINE_V2.replace(b"20.13", b"20.20")]))
    dev.start_connection()
    assert dev.read_data()["zero_point"] == 20.20
    assert dev.read_data()["zero_point"] == 20.20
    # Only one warning
    assert caplog.text.count("zero point of the photometer changed") == 1


def test_tessr_line_in_pieces():
    # Each read returns a piece of a line, as when the timeout expires
    conn = StreamSerial([b"<fH 04606><", b"tA +2987><tO +2481>\r\n", b"<fH 04", b"607>\r\n"])
    dev = TessR(conn, "tess1")
    dev.calibration = 20.5
    # The first try only gets a piece, it is not discarded
    res = dev.read_data(tries=3)
    assert res["freq_sensor"] == 4606.0
    assert res["temp_ambient"] == 29.87
    assert dev.read_data(tries=3)["freq_sensor"] == 4607.0


def test_tess_mac():
    dev = TessR(StreamSerial([]), "tess1")
    # Not in the header if unknown, but needed to register in MQTT
    assert dev.static_conf().mac_address == ""
    assert dev.register_id() == UNKNOWN_MAC
    dev.mac = "AA:BB:CC:DD:EE:FF"
    assert dev.static_conf().mac_address == "AA:BB:CC:DD:EE:FF"
    assert dev.register_id() == "AA:BB:CC:DD:EE:FF"
