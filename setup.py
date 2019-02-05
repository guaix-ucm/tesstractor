
from setuptools import setup

setup(
    name='tesstractor',
    version='0.1dev0',
    author='Sergio Pascual',
    author_email='sergiopr@fis.ucm.es',
    url='https://github.com/guaix-ucm/tesstractor',
    license='GPLv3',
    description='TESS photometer reading software',
    packages=['tesstractor'],
    install_requires=['pytz', 'tzlocal', 'pyserial', 'paho-mqtt', 'attrs'],
    entry_points={
        'console_scripts': [
            'tesstractor = tesstractor.cli:main'
        ]
    },
    zip_safe=False,
    classifiers=[
        "Programming Language :: C",
        "Programming Language :: Cython",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: Implementation :: CPython",
        'Development Status :: 3 - Alpha',
        "Environment :: OtherConf Environment",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: GNU General Public License (GPL)",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering :: Astronomy",
    ],
    long_description=open('README.md').read()
)
