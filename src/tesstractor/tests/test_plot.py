import os

import astropy.table
import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402
import pytz  # noqa: E402

from ..cli import LocationConf  # noqa: E402
from ..plot import do_plots_on_dir, plot_table  # noqa: E402
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


async def test_plot_dir_continues_after_bad_files(tmp_path):
    dev = SQMTest()
    dev.start_connection()
    loc = LocationConf(latitude="40.4189", longitude="-3.6919", elevation="650", timezone="Europe/Madrid")
    sink = FileSink(str(tmp_path), dev.static_conf(), loc, TZ)
    sink.open()
    await sink.send(avg_device_buffer([dict(dev.read_data(), localtz=TZ)]))
    (good,) = os.listdir(tmp_path)
    with open(tmp_path / good) as fd:
        header = [line for line in fd if line.startswith("#")]
    # Sorted before the good file: a new file with only the header and an empty file
    (tmp_path / "00000000_000000_header.dat").write_text("".join(header))
    (tmp_path / "00000000_000001_empty.dat").write_text("")

    failed = do_plots_on_dir(str(tmp_path))
    # The empty file fails, the file with only the header is not plotted
    assert failed == 1
    pngs = sorted(f for f in os.listdir(tmp_path) if f.endswith(".png"))
    assert pngs == [good.replace(".dat", ".png")]
