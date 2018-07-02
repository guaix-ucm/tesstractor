
import math

from ..sqm import average_mags


def test_average_mags():
    mags = [18.0, 18.2, 18.1, 18.3, 18.0, 17.9]
    avg = average_mags(mags)
    assert math.isclose(avg, 18.075134849451306)