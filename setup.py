
from setuptools import setup

setup(
    name='tesstractor',
    version='0.6.dev1',
    author='Sergio Pascual',
    author_email='sergiopr@fis.ucm.es',
    url='https://github.com/guaix-ucm/tesstractor',
    license='GPLv3',
    description='TESS photometer reading software',
    packages=['tesstractor'],
    package_data={
        'tesstractor': ['base.ini', 'IDA-*-template.tpl']
    },
    install_requires=['pytz', 'tzlocal', 'pyserial', 'paho-mqtt', 'attrs>=17.4.0',
                      'matplotlib', 'numpy', 'astroplan', 'astropy'],
    entry_points={
        'console_scripts': [
            'tesstractor = tesstractor.cli:main',
            'tesstractor-plot = tesstractor.plot:main'
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        'Development Status :: 3 - Alpha',
        "Environment :: Console",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: GNU General Public License (GPL)",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering :: Astronomy",
    ],
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown'
)
