"""
Configuration module for AX520 tool.
Contains board definitions and constants used by the programmer.
"""

# Board definitions with flash memory layout and partition information
BOARD_DEFS = {
    'M5_TimerCamera520_V10': {
        'flash_size': 0xF42400,
        'flash_start_addr': 0x3000000,
        'flash_range': (0x3000000, 0x3F42400),
        'partition': {
            'miniboot': 0x3000000,
            'uboot': 0x3006000,
            'env': 0x302F000,
            'kernel': 0x3030000,
            'rootfs': 0x3130000
        }
    },
    'M5_TimerCamera520_V11': {
        'flash_size': 0xF42400,
        'flash_start_addr': 0x3000000,
        'flash_range': (0x3000000, 0x3F42400),
        'partition': {
            'comboot': 0x3000000,
            'kernel': 0x3030000,
            'rootfs': 0x3130000
        }
    }
}

# Default board to use if not specified
DEFAULT_BOARD = 'M5_TimerCamera520_V11'

# Protocol constants
class Protocol:
    """Constants for the AX520 communication protocol."""
    START_BYTE = b'\x02'
    END_BYTE = b'\x03'
    
    # Command codes
    HDBOOT_NOTIFY = 36
    MINIBOOT_NOTIFY = 117
    DEBUG_CMD = 20
    DLOAD_CMD = 24
    WRITE_CMD = 25
    READ_CMD = 26
    RUN_CMD = 27
    ERASE_CMD = 69
    EXECPROG_CMD = 29
    EXIT_CMD = 28  # Added missing EXIT_CMD
    ACK_OK = 5
    ACK_ERR = 10
    
    # Buffer size limitations
    MAX_BUFFER_SIZE = 256
    DEFAULT_PAGE_SIZE = 256

class ProtocolUboot:
    """Constants for the AX520 communication protocol."""
    UBOOT_AUTOBOOT_FLAGE = 'Hit any key to stop autoboot'
    UBOOT_AUTOBOOT_HIT = b' \r\n'
    UBOOT_FLAGE = 'ub#'
    UBOOT_SET_BAUDRATE = 'setenv baudrate {} \r\n'
    UBOOT_SET_BAUDRATE_FLAGE = 'press ENTER'
    UBOOT_H_BAUDRATE = 921600
    UBOOT_DDR = 0x80000000
    UBOOT_DL_PROBE = b'sf probe \r\n'
    UBOOT_ERASE = 'mw.b 0x10800000 0xff {} \r\n'
    UBOOT_WRITE = 'sf update 0x10800000 {} {} \r\n'
    UBOOT_REACEIVE = b'loadx 0x10800000 \r\n'
    UBOOT_REACEIVE_FLAGE = 'C'
    UBOOT_REST = b'reset \r\n'
    UBOOT_BOOT = b'run bootcmd \r\n'

    UBOOT_MEM_WRITE = 'mw.b {} {} {} \r\n'
    UBOOT_MEM_READ = 'md.b {} {} \r\n'

    UBOOT_FLASH_WRITE = 'sf update {} {} {} \r\n'
    UBOOT_FLASH_READ = 'sf read {} {} {} \r\n'
    UBOOT_FLASH_ERASE = 'sf erase {} {} \r\n'
    UBOOT_RESET = b'reset \r\n'

    





