
import math

import pytest

from ..sqm import average_mags
from ..sqm import MEASURE_RE, META_RE, CALIB_RE


def test_average_mags():
    mags = [18.0, 18.2, 18.1, 18.3, 18.0, 17.9]
    avg = average_mags(mags)
    assert math.isclose(avg, 18.075134849451306)


@pytest.mark.parametrize('msg', [
    b'r, 15.79m,0000000042Hz,0000011099c,0000000.024s, 026.7C\r\n',
    b'r, 15.61m,0000000049Hz,0000009384c,0000000.020s,-000.0C\r\n',
    b'r, 06.53m,0000211313Hz,0000000000c,0000000.000s, 027.0C\r\n'
])
def test_data_re1(msg):
    matches = MEASURE_RE.match(msg)
    assert matches


@pytest.mark.parametrize('msg', [
    b'i,00000004,00000003,00000023,00002142\r\n'
])
def test_metadata_re1(msg):
    matches = META_RE.match(msg)
    assert matches


@pytest.mark.parametrize('msg', [
    b'c,00000019.84m,0000151.517s, 022.2C,00000008.71m, 023.2C\r\n'
])
def test_calibration_re1(msg):
    matches = CALIB_RE.match(msg)
    assert matches