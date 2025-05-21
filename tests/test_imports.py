#!/usr/bin/env python3
"""
Simple test to verify that the package structure and imports work correctly.
"""

import sys
import os

# Add the parent directory to the path so we can import the package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def test_imports():
    """Test that all modules can be imported correctly."""
    try:
        # Import the main package
        import ax520tool
        
        # Import individual modules
        from ax520tool import config
        from ax520tool import exceptions
        from ax520tool import board_helper
        from ax520tool import programmer
        from ax520tool import cli
        
        # Import specific classes
        from ax520tool import BoardHelper
        from ax520tool import Programmer
        from ax520tool import AX520ToolException
        
        print("All imports successful!")
        return True
    except ImportError as e:
        print(f"Import error: {e}")
        return False

if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)
