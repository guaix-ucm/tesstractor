
import astropy.io.ascii.core


"""Reader for NSBM files"""


class NightSkyHeader(astropy.io.ascii.core.BaseHeader):
    comment = r'^\s*#\s*'

    def update_meta(self, lines, meta):

        print('meta', meta.keys())
        print('lines', lines)

        return super().update_meta(lines, meta)

    def get_cols(self, lines):

        print('get_cols:lines', lines)
        self.names = ['a', 'b', 'c', 'd', 'e', 'f', 'g']
        self._set_cols_from_names()

        #return super().get_cols(lines)


class NightSkyData(astropy.io.ascii.core.BaseData):
    start_line = 0
    #delimiter = ';'
    comment = r'\s*#'


class NightSky(astropy.io.ascii.core.BaseReader):
    """Read a Night Sky Brightness Measurement file.


    """
    _format_name = 'nsbm'
    _io_registry_can_write = False
    _description = 'Night Sky Brightness Measurement table'

    header_class = NightSkyHeader
    data_class = NightSkyData
    splitter_class = astropy.io.ascii.core.DefaultSplitter
    delimitter = ';'

    def read(self, table):
        """
        Read input data (file-like object, filename, list of strings, or
        single string) into a Table and return the result.
        """
        out = super().read(table)
        # remove the comments
        print('out.meta.c', out.meta['comments'])
        if 'comments' in out.meta:
            del out.meta['comments']
        return out

    def write(self, table):
        raise NotImplementedError


if __name__ == '__main__':

    fname = "20190324_120241_test_sqm1.dat"


    value = NightSky().read(fname)

    print(value)