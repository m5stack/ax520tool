#!/usr/bin/env python3
"""
Example script demonstrating how to use AX520Tool as a library.
"""

import os
import sys
import logging

# Add the parent directory to the path so we can import the package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ax520tool import BoardHelper, Programmer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """
    Example function demonstrating how to use AX520Tool as a library.
    
    This is a simulation - it won't actually connect to a device.
    """
    # Parameters
    port_name = '/dev/ttyUSB0'  # Change this to your actual port
    board_name = 'M5_TimerCamera520_V10'
    firmware_file = 'firmware.bin'  # Change this to your actual firmware file
    address = '0x3000000'  # or use a partition name like 'miniboot'
    
    logger.info(f"Using board: {board_name}")
    logger.info(f"Using port: {port_name}")
    
    try:
        # Initialize board helper
        board_helper = BoardHelper(board_name)
        logger.info(f"Board helper initialized for {board_name}")
        
        # Convert address string to integer
        addr_int = board_helper.number_helper(address)
        logger.info(f"Address {address} converted to {addr_int:#010x}")
        
        # Check if address is valid
        if board_helper.check_flash_addr(addr_int):
            logger.info(f"Address {addr_int:#010x} is valid for this board")
        
        # Initialize programmer (this would connect to a real device)
        logger.info(f"Initializing programmer for port {port_name}")
        programmer = Programmer(port_name=port_name)
        
        # In a real scenario, you would:
        # 1. Open the connection
        # programmer.open_connection()
        # 
        # 2. Perform handshake
        # programmer.handshake()
        # 
        # 3. Read firmware file
        # with open(firmware_file, 'rb') as f:
        #     firmware_data = f.read()
        # 
        # 4. Download firmware
        # programmer.download_firmware(addr_int, firmware_data)
        # 
        # 5. Verify firmware if needed
        # programmer.verify_firmware(addr_int, firmware_data)
        # 
        # 6. Close connection
        # programmer.close_connection()
        
        logger.info("Library usage example completed successfully")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
