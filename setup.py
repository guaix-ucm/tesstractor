#!/usr/bin/env python

from distutils.core import setup

setup(name='pysqml',
      version='3.1',
      author='Miguel Nievas',
      author_email='miguelnievas@ucm.es',
      url='http://guaix.fis.ucm.es/hg/pysqml/',
      license='GPLv3',
      description='SQM reading and plotting software',
      packages=['pysqml'],
      install_requires=['pyephem','numpy','matplotlib', 'pyserial', 'paho-mqtt'],
      classifiers=[
          "Programming Language :: C",
          "Programming Language :: Cython",
          "Programming Language :: Python :: 3.6",
          "Programming Language :: Python :: Implementation :: CPython",
          'Development Status :: 3 - Alpha',
          "Environment :: Other Environment",
          "Intended Audience :: Science/Research",
          "License :: OSI Approved :: GNU General Public License (GPL)",
          "Operating System :: OS Independent",
          "Topic :: Scientific/Engineering :: Astronomy",
      ],
      long_description=open('README.txt').read()
      )
