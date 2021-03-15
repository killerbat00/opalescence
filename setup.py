# !/usr/bin/env python
# -*- coding: utf-8 -*-

"""
setuptools script for opalescence
"""
from setuptools import setup

import opalescence

with open("README.md") as readme_file:
    readme = readme_file.read()

requirements = [
    "requests", "aiohttp", "bitstring",
]

setup(
    name="opalescence",
    version=opalescence.__version__,
    description="A torrent client written using Python 3 and asyncio",
    long_description=readme,
    author="brian houston morrow",
    author_email="bhm@brianmorrow.net",
    url="https://github.com/killerbat00/opalescence",
    packages=["opalescence"],
    install_requires=requirements,
    license="MIT license",
    zip_safe=False,
    keywords="torrent",
    classifiers=[
        "Development Status :: 4 - Beta",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.9"
    ],
    test_suite="tests",
    include_package_data=True,
)
