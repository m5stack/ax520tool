"""
Board helper module for AX520 tool.
Provides utilities for board-specific operations and validations.
"""

from typing import Tuple, Dict, Any, Union, Optional
from .config import BOARD_DEFS, DEFAULT_BOARD
from .exceptions import InvalidFlashRangeException, InvalidNumberFormatException

import logging
logger = logging.getLogger(__name__)


class BoardHelper:
    """Helper class for board-specific operations and validations."""
    
    def __init__(self, board_name: str = DEFAULT_BOARD):
        """
        Initialize the board helper with the specified board name.
        
        Args:
            board_name: Name of the board to use
        """
        self.board_name = board_name
        if board_name not in BOARD_DEFS:
            logger.warning(f'Unable to locate the board {board_name}, falling back to default.')
            self.board_name = DEFAULT_BOARD
        self.defs = BOARD_DEFS[self.board_name]

    @staticmethod
    def in_range(value: int, range_tuple: Tuple[int, int]) -> bool:
        """
        Check if a value is within the specified range.
        
        Args:
            value: Value to check
            range_tuple: Range tuple (min, max)
            
        Returns:
            True if value is within range, False otherwise
        """
        return range_tuple[0] <= value <= range_tuple[1]

    def check_flash_addr(self, addr: int, end_addr: Optional[int] = None, 
                         size: Optional[int] = None, partition: Optional[str] = None) -> bool:
        """
        Check if a flash address is valid for the current board.
        
        Args:
            addr: Flash address to check
            end_addr: End address (optional)
            size: Size in bytes (optional)
            partition: Partition name (optional)
            
        Returns:
            True if address is valid
            
        Raises:
            InvalidFlashRangeException: If address is outside valid range
            InvalidNumberFormatException: If partition name is invalid
        """
        if not self.in_range(addr, self.defs['flash_range']):
            raise InvalidFlashRangeException(addr, self.defs['flash_range'])
        
        if end_addr is not None:
            if not self.in_range(end_addr, self.defs['flash_range']):
                raise InvalidFlashRangeException(end_addr, self.defs['flash_range'])
        
        if size is not None:
            if not self.in_range(addr + size - 1, self.defs['flash_range']):
                raise InvalidFlashRangeException(addr + size - 1, self.defs['flash_range'])
        
        # Check not passing sector with name erase
        if partition:
            if partition in self.defs['partition']:
                partition_addr = self.defs['partition'][partition]
                
                # Check if operation would overlap with other partitions
                for part_name, part_addr in self.defs['partition'].items():
                    if part_name == partition:
                        continue
                        
                    # Calculate partition sizes (approximate based on next partition)
                    if size is not None:
                        # Check if our operation overlaps with another partition
                        operation_end = partition_addr + size - 1
                        
                        # If another partition starts within our operation range
                        if part_addr > partition_addr and part_addr <= operation_end:
                            raise InvalidFlashRangeException(
                                part_addr, 
                                (partition_addr, operation_end)
                            )
                        
                        # If our operation starts within another partition's range
                        # (This is a simplification as we don't know other partitions' sizes)
                        if part_addr < partition_addr and part_addr > addr:
                            raise InvalidFlashRangeException(
                                addr,
                                (part_addr, part_addr)  # We don't know the end
                            )
            else:
                raise InvalidNumberFormatException(partition)

        return True

    def number_helper(self, number_or_str: str) -> int:
        """
        Convert a string to a number, handling hex, decimal, and partition names.
        
        Args:
            number_or_str: String to convert
            
        Returns:
            Integer value
            
        Raises:
            InvalidNumberFormatException: If string cannot be converted to a number
        """
        number_or_str = number_or_str.strip()

        # Check if partition name
        if number_or_str in self.defs['partition']:
            return self.defs['partition'][number_or_str]

        # Check if hex
        if number_or_str.startswith('0x'):
            try:
                return int(number_or_str, 16)
            except ValueError:
                raise InvalidNumberFormatException(number_or_str)
        
        # Try decimal
        try:
            return int(number_or_str)
        except ValueError:
            raise InvalidNumberFormatException(number_or_str)
