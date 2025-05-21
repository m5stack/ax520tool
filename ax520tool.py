#!/usr/bin/env python3
"""
AX520 Tool - Main entry point.
This is a wrapper script that calls the main function from the ax520tool package.
"""

import sys
from ax520tool.cli import main

if __name__ == "__main__":
    sys.exit(main())
