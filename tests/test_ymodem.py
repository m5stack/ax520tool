"""
Test module for the custom YMODEM implementation.
"""

import os
import sys
import unittest
import tempfile
from unittest.mock import MagicMock, patch

# Add parent directory to path to import ax520tool modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ax520tool.ymodem import (
    ProtocolType, ProtocolSubType, ModemSocket, 
    calc_crc16, calc_checksum, TransmissionTask
)


class TestYmodem(unittest.TestCase):
    """Test cases for the custom YMODEM implementation."""

    def test_calc_crc16(self):
        """Test CRC-16 calculation."""
        # Test with known values for our implementation
        self.assertEqual(calc_crc16(b'123456789'), 0x31C3)
        self.assertEqual(calc_crc16(b''), 0)
        self.assertEqual(calc_crc16(b'A'), 0x58E5)

    def test_calc_checksum(self):
        """Test simple checksum calculation."""
        # Test with known values for our implementation
        self.assertEqual(calc_checksum(b'123456789'), 0xDD)
        self.assertEqual(calc_checksum(b''), 0)
        self.assertEqual(calc_checksum(b'A'), 0x41)

    def test_transmission_task_init(self):
        """Test TransmissionTask initialization."""
        # Create a temporary file for testing
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as temp_file:
            temp_file_path = temp_file.name
            temp_file.write(b'Test data')
            temp_file.flush()

        try:
            # Test with file
            task = TransmissionTask(temp_file_path)
            self.assertEqual(task.name, os.path.basename(temp_file_path))
            self.assertEqual(task.total, 9)  # 'Test data' is 9 bytes
            self.assertEqual(task.sent, 0)
            self.assertEqual(task.received, 0)

            # Test without file
            task = TransmissionTask()
            self.assertEqual(task.name, '')
            self.assertEqual(task.total, 0)
            self.assertEqual(task.sent, 0)
            self.assertEqual(task.received, 0)
        finally:
            # Clean up
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    def test_modem_socket_init(self):
        """Test ModemSocket initialization."""
        # Mock read and write functions
        read_func = MagicMock()
        write_func = MagicMock()

        # Test default initialization
        modem = ModemSocket(read_func, write_func)
        self.assertEqual(modem.protocol_type, ProtocolType.YMODEM)
        self.assertEqual(modem.protocol_subtype, ProtocolSubType.YMODEM_BATCH_FILE_TRANSMISSION)
        self.assertEqual(modem._packet_size, 1024)

        # Test with custom parameters
        modem = ModemSocket(
            read_func, 
            write_func, 
            protocol_type=ProtocolType.XMODEM,
            protocol_type_options=['g'],
            packet_size=128
        )
        self.assertEqual(modem.protocol_type, ProtocolType.XMODEM)
        self.assertEqual(modem._packet_size, 128)

        # Test with YMODEM-G
        modem = ModemSocket(
            read_func, 
            write_func, 
            protocol_type=ProtocolType.YMODEM,
            protocol_type_options=['g'],
            packet_size=1024
        )
        self.assertEqual(modem.protocol_type, ProtocolType.YMODEM)
        self.assertEqual(modem.protocol_subtype, ProtocolSubType.YMODEM_G_FILE_TRANSMISSION)
        self.assertEqual(modem._packet_size, 1024)

    @patch('ax520tool.ymodem.ModemSocket._read_and_wait')
    @patch('ax520tool.ymodem.ModemSocket.write')
    def test_modem_socket_send_header(self, mock_write, mock_read_and_wait):
        """Test ModemSocket send header creation."""
        # Mock read and write functions
        read_func = MagicMock()
        write_func = MagicMock()
        
        # Create ModemSocket instance
        modem = ModemSocket(read_func, write_func)
        
        # Test header creation for 128-byte packet
        header = modem._make_send_header(128, 1)
        self.assertEqual(header, bytearray([0x01, 0x01, 0xFE]))
        
        # Test header creation for 1024-byte packet
        header = modem._make_send_header(1024, 2)
        self.assertEqual(header, bytearray([0x02, 0x02, 0xFD]))

    @patch('ax520tool.ymodem.ModemSocket._read_and_wait')
    @patch('ax520tool.ymodem.ModemSocket.write')
    def test_modem_socket_send_checksum(self, mock_write, mock_read_and_wait):
        """Test ModemSocket checksum creation."""
        # Mock read and write functions
        read_func = MagicMock()
        write_func = MagicMock()
        
        # Create ModemSocket instance
        modem = ModemSocket(read_func, write_func)
        
        # Test CRC-16 checksum
        data = b'Test data'
        checksum = modem._make_send_checksum(1, data)
        crc_value = calc_crc16(data)
        self.assertEqual(checksum, bytearray([crc_value >> 8, crc_value & 0xff]))
        
        # Test simple checksum
        checksum = modem._make_send_checksum(0, data)
        simple_checksum = calc_checksum(data)
        self.assertEqual(checksum, bytearray([simple_checksum]))


if __name__ == '__main__':
    unittest.main()
