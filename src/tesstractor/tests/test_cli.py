
import pkgutil
from ..cli import main


def test_config(capsys):
    dtm = pkgutil.get_data('tesstractor', 'base.ini')
    data = dtm.decode('utf-8')
    main(['-g'])
    out, err = capsys.readouterr()
    # last character in out is \n
    assert data == out[:-1]
