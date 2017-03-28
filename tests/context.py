#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Provides a context for test files so the package's files will be resolved properly
"""

import os
import sys

path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

