#!/usr/bin/env python3
import os
import sys

print(f"SUCCESS: Script executed. ENV: {os.environ.get('TEST_JOB', '')}, PARAM: {os.environ.get('TEST_PARAM', '')}")
sys.exit(0) 