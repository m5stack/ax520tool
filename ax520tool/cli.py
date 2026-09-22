"""
Command-line interface module for AX520 tool.
"""

import argparse
import logging
import os
import sys
import tempfile
import zipfile
import glob
import json
import shutil
import math
from typing import List, Dict, Any, Optional, Tuple

from .board_helper import BoardHelper
# from .programmer import Programmer, UbootProgrammer
from .programmer import Programmer
from .UbootProgrammer import UbootProgrammer
from .config import DEFAULT_BOARD
from .exceptions import (
    AX520ToolException,
    FileNotFoundException,
    InvalidNumberFormatException,
    SerialConnectionException,
    HandshakeFailedException
)

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """
    Set up logging configuration.
    
    Args:
        verbose: Whether to enable verbose logging
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()
        ]
    )


def parse_args(args: List[str] = None) -> argparse.Namespace:
    """
    Parse command-line arguments.
    
    Args:
        args: Command-line arguments (optional)
        
    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(description="AX520 programmer tool")
    parser.add_argument("-b", "--board", default=DEFAULT_BOARD, help="Board name")
    parser.add_argument("-p", "--port", required=True, help="Serial port name")
    parser.add_argument("-r", "--reboot", help="Reboot after flashing", action="store_true")
    parser.add_argument("-c", "--check", help="Verify firmware after flashing", action="store_true")
    parser.add_argument("-e", "--erase-env", help="Erase env partition before any operation", action="store_true")
    parser.add_argument("-v", "--verbose", help="Enable verbose logging", action="store_true")
    parser.add_argument("-u", "--uboot", help="Enable uboot programmer", action="store_true")
    parser.add_argument("-i", "--image", help="ax520 Image file path")


    subparsers = parser.add_subparsers(dest='command', help='Operations')

    # Write flash command
    write_flash_parser = subparsers.add_parser('write_flash', help='Download firmware to the device')
    write_flash_parser.add_argument('flash_args', nargs='+', help='Address and firmware file pairs')

    # Read flash command
    read_flash_parser = subparsers.add_parser('read_flash', help='Read firmware from the device')
    read_flash_parser.add_argument('address', help='Starting address of the device')
    read_flash_parser.add_argument('size', help='Size of reading')
    read_flash_parser.add_argument('output_file', help='Location of the output file')

    # Erase flash command
    erase_flash_parser = subparsers.add_parser('erase_flash', help='Erase flash of the device')
    erase_flash_parser.add_argument('address', help='Starting address of the device')
    erase_flash_parser.add_argument('size', help='Size of reading')

    return parser.parse_args(args)


def validate_write_flash_args(args: argparse.Namespace, board_helper: BoardHelper) -> List[Tuple[int, str]]:
    """
    Validate write_flash command arguments.
    
    Args:
        args: Parsed arguments
        board_helper: Board helper instance
        
    Returns:
        List of (address, firmware_file) tuples
        
    Raises:
        ValueError: If arguments are invalid
        FileNotFoundException: If firmware file not found
    """
    flash_args = args.flash_args
    if len(flash_args) % 2 != 0:
        raise ValueError("The argument list must be pairs of address and firmware file")
        
    str_pairs = list(zip(flash_args[::2], flash_args[1::2]))
    pairs = []
    
    # Validate addresses and firmware files
    for address_str, firmware_file in str_pairs:
        address = board_helper.number_helper(address_str)
        board_helper.check_flash_addr(address)
        
        if not os.path.exists(firmware_file):
            raise FileNotFoundException(firmware_file)
            
        pairs.append((address, firmware_file))
        
    return pairs


def erase_env_partition(programmer: Programmer, board_helper: BoardHelper) -> bool:
    """
    Erase the env partition if it exists.
    
    Args:
        programmer: Programmer instance
        board_helper: Board helper instance
        
    Returns:
        True if erased successfully or no env partition, False otherwise
    """
    if 'env' in board_helper.defs['partition']:
        env_addr = board_helper.defs['partition']['env']
        
        # Calculate size: difference between env address and next partition
        next_addr = None
        for part, addr in board_helper.defs['partition'].items():
            if addr > env_addr and (next_addr is None or addr < next_addr):
                next_addr = addr
        
        if next_addr is None:
            # If env is the last partition, use 64KB as default size
            env_size = 64 * 1024
        else:
            env_size = next_addr - env_addr
        
        logger.info(f"Erasing env partition at address {env_addr:#010x}, size {env_size:#010x} bytes")
        if not programmer.erase(env_addr, env_size):
            logger.error("Failed to erase env partition")
            return False
            
        logger.info("Env partition erased successfully")
    else:
        logger.warning("No env partition found for this board")
        
    return True


def handle_write_flash(args: argparse.Namespace, programmer: Programmer, board_helper: BoardHelper) -> bool:
    """
    Handle write_flash command.
    
    Args:
        args: Parsed arguments
        programmer: Programmer instance
        board_helper: Board helper instance
        
    Returns:
        True if successful, False otherwise
    """
    try:
        pairs = validate_write_flash_args(args, board_helper)
    except (ValueError, FileNotFoundException) as e:
        logger.error(str(e))
        return False
    
    for address, firmware_file in pairs:
        with open(firmware_file, 'rb') as f:
            firmware_data = f.read()

        try:
            board_helper.check_flash_addr(address, size=len(firmware_data))
        except AX520ToolException as e:
            logger.error(str(e))
            return False

        logger.info(f"Downloading {firmware_file} to address {address:#010x}")
        if not programmer.download_firmware(address, firmware_data, autostart=False):
            logger.error("Firmware download failed")
            return False
            
        if args.check:
            if not programmer.verify_firmware(address, firmware_data):
                logger.error("Firmware verification failed")
                return False
    
    return True


def handle_read_flash(args: argparse.Namespace, programmer: Programmer, board_helper: BoardHelper) -> bool:
    """
    Handle read_flash command.
    
    Args:
        args: Parsed arguments
        programmer: Programmer instance
        board_helper: Board helper instance
        
    Returns:
        True if successful, False otherwise
    """
    try:
        address = board_helper.number_helper(args.address)
        size = board_helper.number_helper(args.size)
        board_helper.check_flash_addr(address, size=size)
    except AX520ToolException as e:
        logger.error(str(e))
        return False
    
    firmware = programmer.dump_firmware(address, size)
    if firmware is None:
        logger.error("Failed to read firmware")
        return False
    
    try:
        with open(args.output_file, 'wb') as f:
            f.write(firmware)
        logger.info(f"Firmware saved to {args.output_file}")
    except Exception as e:
        logger.error(f"Failed to write output file: {e}")
        return False
    
    return True


def handle_erase_flash(args: argparse.Namespace, programmer: Programmer, board_helper: BoardHelper) -> bool:
    """
    Handle erase_flash command.
    
    Args:
        args: Parsed arguments
        programmer: Programmer instance
        board_helper: Board helper instance
        
    Returns:
        True if successful, False otherwise
    """
    try:
        address = board_helper.number_helper(args.address)
        size = board_helper.number_helper(args.size)
        board_helper.check_flash_addr(address, size=size)
    except AX520ToolException as e:
        logger.error(str(e))
        return False
    
    logger.info(f"Erasing memory at address {address:#010x}, size {size:#010x} bytes")
    if not programmer.erase(address, size):
        logger.error("Failed to erase memory")
        return False
    
    return True

def handle_write_image(args: argparse.Namespace, programmer: Programmer, board_helper: BoardHelper) -> bool:
    """
    Handle write_image command.
    Parse ax520_image file and flash comboot, kernel, rootfs in order.
    
    Args:
        args: Parsed arguments
        programmer: Programmer instance
        board_helper: Board helper instance
        
    Returns:
        True if successful, False otherwise
    """
    # Check if image file path is provided
    if not args.image:
        logger.error("No image file path provided with -i option")
        return False
    
    # Check if image file exists
    if not os.path.exists(args.image):
        logger.error(f"Image file not found: {args.image}")
        return False
    
    temp_dir = tempfile.mkdtemp()
    try:
        with zipfile.ZipFile(args.image, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        json_files = glob.glob(os.path.join(temp_dir, '*.json'))
        if len(json_files) < 1:
            logger.error(f"Invalid ax520_image file: {args.image}")
            return False
        with open(json_files[0], 'r') as f:
            image_config = json.load(f)
        if 'IMAGE_LIST' not in image_config:
            logger.error(f"Invalid ax520_image file: {json_files[0]}")
            return False
        image_lists = image_config['IMAGE_LIST']
        for index,image in enumerate(image_lists):
            if 'comboot' == image['PARTITION']:
                firmware_file = os.path.join(temp_dir, image['IMAGE_NAME'])
                partition = image['PARTITION']
                if 'IMAGE_ADDR' in image:
                    address = int(image['IMAGE_ADDR'], 16)
                else:
                    address = board_helper.defs['partition'][partition]
                logger.info(f"Downloading {firmware_file} to address {address:#010x}")
                with open(firmware_file, 'rb') as f:
                    firmware_data = f.read()
                if not programmer.erase(address, math.ceil(len(firmware_data) / 65536) * 65536):
                    logger.error("Failed to erase flash")
                    return False
                if not programmer.download_firmware(address, firmware_data, autostart=False):
                    logger.error("Firmware download failed")
                    return False
                del image_lists[index]
                if not args.uboot:
                    programmer.run(board_helper.defs['flash_start_addr'])
                    programmer.close_connection()
                    programmer = UbootProgrammer(port_name=args.port, timeout=0.1)
                    if not programmer.open_connection():
                        logger.error("Failed to open serial port")
                        return False
                    
                    logger.info("Starting handshake with the uboot...")
                    if not programmer.handshake(timeout=10):
                        logger.error("Handshake failed")
                        programmer.close_connection()
                        return False
                break
        
        for image in image_lists:
            firmware_file = os.path.join(temp_dir, image['IMAGE_NAME'])
            partition = image['PARTITION']
            if 'IMAGE_ADDR' in image:
                address = int(image['IMAGE_ADDR'], 16)
            else:
                address = board_helper.defs['partition'][partition]
            logger.info(f"Downloading {firmware_file} to address {address:#010x}")
            with open(firmware_file, 'rb') as f:
                firmware_data = f.read()
            if not programmer.download_firmware(address, firmware_data, autostart=False):
                logger.error("Firmware download failed")
                return False
    except Exception as e:
        logger.error(f"Image file : {args.image} extra failed: {e}")
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    logger.info("All partitions flashed successfully")
    return True


def run_command(args: argparse.Namespace) -> bool:
    """
    Run the specified command.
    
    Args:
        args: Parsed arguments
        
    Returns:
        True if successful, False otherwise
    """
    board_helper = BoardHelper(args.board)
    
    # If image option is provided, use image flashing mode
    if args.image:
        # Image flashing doesn't require a specific command
        pass
    elif not args.command:
        logger.error("No command specified")
        return False
    
    programmer = UbootProgrammer(port_name=args.port, timeout=0.1) if args.uboot else Programmer(port_name=args.port, timeout=0.1)
    
    try:
        if not programmer.open_connection():
            logger.error("Failed to open serial port")
            return False
        
        logger.info("Starting handshake with the device...")
        if not programmer.handshake(timeout=10):
            logger.error("Handshake failed")
            programmer.close_connection()
            return False
        
        # Erase env partition if requested
        if args.erase_env:
            if not erase_env_partition(programmer, board_helper):
                programmer.close_connection()
                return False
        
        # Execute the requested command
        success = False
        if args.command == 'write_flash':
            success = handle_write_flash(args, programmer, board_helper)
        elif args.command == 'read_flash':
            success = handle_read_flash(args, programmer, board_helper)
        elif args.command == 'erase_flash':
            success = handle_erase_flash(args, programmer, board_helper)
        elif args.image:
            success = handle_write_image(args, programmer, board_helper)
        else:
            logger.error(f"Unknown command: {args.command}")
            programmer.close_connection()
            return False
        
        if not success:
            programmer.close_connection()
            return False
        
        # Reboot if requested
        if args.reboot:
            logger.info("Rebooting device")
            if not programmer.run(board_helper.defs['flash_start_addr']):
                logger.error("Failed to reboot the device")
            else:
                programmer.handshook = False
        
        programmer.close_connection()
        logger.info("Operation completed successfully")
        return True
        
    except (SerialConnectionException, HandshakeFailedException) as e:
        logger.error(str(e))
        if programmer.serial_port:
            programmer.close_connection()
        return False
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if programmer.serial_port:
            programmer.close_connection()
        return False


def main() -> int:
    """
    Main entry point for the CLI.
    
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    args = parse_args()
    setup_logging(args.verbose)
    
    try:
        if run_command(args):
            return 0
        else:
            return 1
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
