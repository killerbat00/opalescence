# !/usr/bin/env python
# -*- coding: utf-8 -*-

"""
setuptools script for opalescence
"""

from setuptools import setup

with open("README.md") as readme_file:
    readme = readme_file.read()

with open("VERSION") as version_file:
    version = version_file.read()

requirements = [
    "requests", 'aiohttp'
]

setup(
    name="opalescence",
    version=version,
    description="Torrent client offering basic functionality.",
    long_description=readme,
    author="brian houston morrow",
    author_email="bhm@brianmorrow.net",
    url="https://github.com/killerbat00/opalescence",
    packages=[
        "opalescence"
    ],
    package_dir={"opalescence": "opalescence"},
    install_requires=requirements,
    license="MIT license",
    zip_safe=False,
    keywords="torrent",
    classifiers=[
        "Development Status :: 4 - Beta",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Programming Language :: Python :: 3.6"
    ],
    test_suite="tests",
)
