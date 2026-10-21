import os

import astropy.table
import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402
import pytz  # noqa: E402

from ..cli import LocationConf  # noqa: E402
from ..plot import plot_table  # noqa: E402
from ..sqm import SQMTest  # noqa: E402
from ..writef import FileSink  # noqa: E402
from ..workers import avg_device_buffer  # noqa: E402

TZ = pytz.timezone("Europe/Madrid")


async def test_plot_single_point(tmp_path):
    dev = SQMTest()
    dev.start_connection()
    loc = LocationConf(latitude="40.4189", longitude="-3.6919", elevation="650", timezone="Europe/Madrid")
    sink = FileSink(str(tmp_path), dev.static_conf(), loc, TZ)
    sink.open()
    await sink.send(avg_device_buffer([dict(dev.read_data(), localtz=TZ)]))
    (fname,) = os.listdir(tmp_path)

    tab = astropy.table.Table.read(str(tmp_path / fname), format="ascii.IDA")
    fig = plot_table(tab)
    xmin, xmax = fig.axes[0].get_xlim()
    plt.close(fig)
    # A single point must not expand the time axis by years
    assert (mdates.num2date(xmax) - mdates.num2date(xmin)).total_seconds() == pytest.approx(7200)
