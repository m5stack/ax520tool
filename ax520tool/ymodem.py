"""
Custom YMODEM protocol implementation for AX520 tool.
This module replaces the external ymodem library dependency.
"""

import logging
import os
import sys
import time
from enum import IntEnum
from typing import Any, Callable, List, Optional, Tuple, Union, BinaryIO

logger = logging.getLogger(__name__)

# YMODEM protocol constants
SOH = b'\x01'  # Start of 128-byte data packet
STX = b'\x02'  # Start of 1024-byte data packet
EOT = b'\x04'  # End of transmission
ACK = b'\x06'  # Acknowledge
NAK = b'\x15'  # Negative acknowledge
CAN = b'\x18'  # Cancel transmission
CRC = b'\x43'  # 'C' - Request 16-bit CRC
G   = b'\x67'  # 'g' - Request YMODEM-G file transfer


class ProtocolType(IntEnum):
    """Protocol types supported by the YMODEM implementation."""
    XMODEM = 0
    YMODEM = 1
    ZMODEM = 2  # Not implemented

    @classmethod
    def all(cls) -> List[int]:
        """Return all supported protocol types."""
        return [
            cls.XMODEM,
            cls.YMODEM
        ]


class ProtocolSubType(IntEnum):
    """YMODEM protocol subtypes."""
    YMODEM_BATCH_FILE_TRANSMISSION = 0
    YMODEM_G_FILE_TRANSMISSION = 1


# CRC-16-CCITT lookup table
CRC16_TABLE = [
    0x0000, 0x1021, 0x2042, 0x3063, 0x4084, 0x50a5, 0x60c6, 0x70e7,
    0x8108, 0x9129, 0xa14a, 0xb16b, 0xc18c, 0xd1ad, 0xe1ce, 0xf1ef,
    0x1231, 0x0210, 0x3273, 0x2252, 0x52b5, 0x4294, 0x72f7, 0x62d6,
    0x9339, 0x8318, 0xb37b, 0xa35a, 0xd3bd, 0xc39c, 0xf3ff, 0xe3de,
    0x2462, 0x3443, 0x0420, 0x1401, 0x64e6, 0x74c7, 0x44a4, 0x5485,
    0xa56a, 0xb54b, 0x8528, 0x9509, 0xe5ee, 0xf5cf, 0xc5ac, 0xd58d,
    0x3653, 0x2672, 0x1611, 0x0630, 0x76d7, 0x66f6, 0x5695, 0x46b4,
    0xb75b, 0xa77a, 0x9719, 0x8738, 0xf7df, 0xe7fe, 0xd79d, 0xc7bc,
    0x48c4, 0x58e5, 0x6886, 0x78a7, 0x0840, 0x1861, 0x2802, 0x3823,
    0xc9cc, 0xd9ed, 0xe98e, 0xf9af, 0x8948, 0x9969, 0xa90a, 0xb92b,
    0x5af5, 0x4ad4, 0x7ab7, 0x6a96, 0x1a71, 0x0a50, 0x3a33, 0x2a12,
    0xdbfd, 0xcbdc, 0xfbbf, 0xeb9e, 0x9b79, 0x8b58, 0xbb3b, 0xab1a,
    0x6ca6, 0x7c87, 0x4ce4, 0x5cc5, 0x2c22, 0x3c03, 0x0c60, 0x1c41,
    0xedae, 0xfd8f, 0xcdec, 0xddcd, 0xad2a, 0xbd0b, 0x8d68, 0x9d49,
    0x7e97, 0x6eb6, 0x5ed5, 0x4ef4, 0x3e13, 0x2e32, 0x1e51, 0x0e70,
    0xff9f, 0xefbe, 0xdfdd, 0xcffc, 0xbf1b, 0xaf3a, 0x9f59, 0x8f78,
    0x9188, 0x81a9, 0xb1ca, 0xa1eb, 0xd10c, 0xc12d, 0xf14e, 0xe16f,
    0x1080, 0x00a1, 0x30c2, 0x20e3, 0x5004, 0x4025, 0x7046, 0x6067,
    0x83b9, 0x9398, 0xa3fb, 0xb3da, 0xc33d, 0xd31c, 0xe37f, 0xf35e,
    0x02b1, 0x1290, 0x22f3, 0x32d2, 0x4235, 0x5214, 0x6277, 0x7256,
    0xb5ea, 0xa5cb, 0x95a8, 0x8589, 0xf56e, 0xe54f, 0xd52c, 0xc50d,
    0x34e2, 0x24c3, 0x14a0, 0x0481, 0x7466, 0x6447, 0x5424, 0x4405,
    0xa7db, 0xb7fa, 0x8799, 0x97b8, 0xe75f, 0xf77e, 0xc71d, 0xd73c,
    0x26d3, 0x36f2, 0x0691, 0x16b0, 0x6657, 0x7676, 0x4615, 0x5634,
    0xd94c, 0xc96d, 0xf90e, 0xe92f, 0x99c8, 0x89e9, 0xb98a, 0xa9ab,
    0x5844, 0x4865, 0x7806, 0x6827, 0x18c0, 0x08e1, 0x3882, 0x28a3,
    0xcb7d, 0xdb5c, 0xeb3f, 0xfb1e, 0x8bf9, 0x9bd8, 0xabbb, 0xbb9a,
    0x4a75, 0x5a54, 0x6a37, 0x7a16, 0x0af1, 0x1ad0, 0x2ab3, 0x3a92,
    0xfd2e, 0xed0f, 0xdd6c, 0xcd4d, 0xbdaa, 0xad8b, 0x9de8, 0x8dc9,
    0x7c26, 0x6c07, 0x5c64, 0x4c45, 0x3ca2, 0x2c83, 0x1ce0, 0x0cc1,
    0xef1f, 0xff3e, 0xcf5d, 0xdf7c, 0xaf9b, 0xbfba, 0x8fd9, 0x9ff8,
    0x6e17, 0x7e36, 0x4e55, 0x5e74, 0x2e93, 0x3eb2, 0x0ed1, 0x1ef0,
]


def calc_crc16(data: Union[bytes, bytearray], crc: int = 0) -> int:
    """
    Calculate CRC-16-CCITT for the given data.
    
    Args:
        data: Data bytes to calculate CRC for
        crc: Initial CRC value (default: 0)
        
    Returns:
        Calculated CRC-16 value
    """
    # Standard CRC-16-CCITT implementation
    for byte in bytearray(data):
        crc = ((crc << 8) & 0xFF00) ^ CRC16_TABLE[((crc >> 8) ^ byte) & 0xFF]
    return crc & 0xFFFF


def calc_checksum(data: Union[bytes, bytearray], checksum: int = 0) -> int:
    """
    Calculate simple checksum for the given data.
    
    Args:
        data: Data bytes to calculate checksum for
        checksum: Initial checksum value (default: 0)
        
    Returns:
        Calculated checksum value
    """
    # For XMODEM/YMODEM, the checksum is the sum of all bytes modulo 256
    total = checksum
    for byte in bytearray(data):
        total = (total + byte) & 0xFF
    return total


class TransmissionTask:
    """Represents a file transmission task for YMODEM protocol."""
    
    def __init__(self, path: Optional[str] = None):
        """
        Initialize a transmission task.
        
        Args:
            path: Path to the file to transmit (optional)
        """
        self._path = path or ""
        self._name = os.path.basename(path) if path else ""
        self._mtime = int(os.path.getmtime(path)) if path else 0
        self._mode = 0
        self._sn = 0

        self._total_length = os.path.getsize(path) if path else 0
        self._sent_length = 0
        self._received_length = 0
        self._success_packet_count = 0

    @property
    def path(self) -> str:
        """Get the file path."""
        return self._path

    @property
    def name(self) -> str:
        """Get the file name."""
        return self._name
    
    @name.setter
    def name(self, v: str):
        """Set the file name."""
        self._name = v

    @property
    def total(self) -> int:
        """Get the total file size in bytes."""
        return self._total_length
    
    @total.setter
    def total(self, v: int):
        """Set the total file size in bytes."""
        self._total_length = v

    @property
    def sent(self) -> int:
        """Get the number of bytes sent."""
        return self._sent_length
    
    @sent.setter
    def sent(self, v: int):
        """Set the number of bytes sent."""
        self._sent_length = v

    @property
    def received(self) -> int:
        """Get the number of bytes received."""
        return self._received_length
    
    @received.setter
    def received(self, v: int):
        """Set the number of bytes received."""
        self._received_length = v

    @property
    def mtime(self) -> int:
        """Get the file modification time."""
        return self._mtime
    
    @mtime.setter
    def mtime(self, v: int):
        """Set the file modification time."""
        self._mtime = v

    @property
    def mode(self) -> int:
        """Get the file mode."""
        return self._mode
    
    @mode.setter
    def mode(self, v: int):
        """Set the file mode."""
        self._mode = v

    @property
    def sn(self) -> int:
        """Get the serial number."""
        return self._sn
    
    @sn.setter
    def sn(self, v: int):
        """Set the serial number."""
        self._sn = v

    @property
    def success_packet_count(self) -> int:
        """Get the number of successfully transmitted packets."""
        return self._success_packet_count
    
    @success_packet_count.setter
    def success_packet_count(self, v: int):
        """Set the number of successfully transmitted packets."""
        self._success_packet_count = v


class ModemSocket:
    """
    YMODEM protocol implementation for file transfer.
    This class replaces the ymodem.Socket.ModemSocket class.
    """
    
    def __init__(self, 
                 read_func: Callable[[int, Optional[float]], Any], 
                 write_func: Callable[[Union[bytes, bytearray], Optional[float]], Any], 
                 protocol_type: int = ProtocolType.YMODEM, 
                 protocol_type_options: List[str] = [],
                 packet_size: int = 1024):
        """
        Initialize the YMODEM protocol handler.
        
        Args:
            read_func: Function to read data from the communication channel
            write_func: Function to write data to the communication channel
            protocol_type: Protocol type (XMODEM or YMODEM)
            protocol_type_options: Protocol options (e.g., ['g'] for YMODEM-G)
            packet_size: Packet size (128 or 1024 bytes)
        """
        self.logger = logging.getLogger('ModemSocket')
        
        self._read = read_func
        self._write = write_func
        
        # Set protocol parameters
        if protocol_type not in ProtocolType.all():
            raise ValueError(f"Invalid protocol type: {protocol_type}")
        
        self.protocol_type = protocol_type
        self._packet_size = packet_size if packet_size in [128, 1024] else 1024
        
        # Set protocol subtype
        if self.protocol_type == ProtocolType.YMODEM:
            if 'g' in protocol_type_options:
                self.protocol_subtype = ProtocolSubType.YMODEM_G_FILE_TRANSMISSION
            else:
                self.protocol_subtype = ProtocolSubType.YMODEM_BATCH_FILE_TRANSMISSION
        else:
            self.protocol_subtype = None
            
        # Set protocol features
        self._use_length_field = True
        self._use_date_field = True
        self._use_mode_field = True
        self._use_sn_field = False
        
    def read(self, size: int, timeout: float = 1) -> Any:
        """
        Read data from the communication channel.
        
        Args:
            size: Number of bytes to read
            timeout: Read timeout in seconds
            
        Returns:
            Read data or None if timeout
        """
        try:
            return self._read(size, timeout)
        except Exception as e:
            self.logger.warning(f"[Modem]: Read timeout! {e}")
            return None
    
    def write(self, data: Union[bytes, bytearray], timeout: float = 1) -> Any:
        """
        Write data to the communication channel.
        
        Args:
            data: Data to write
            timeout: Write timeout in seconds
            
        Returns:
            Result of the write operation or None if timeout
        """
        try:
            return self._write(data, timeout)
        except Exception as e:
            self.logger.warning(f"[Modem]: Write timeout! {e}")
            return None
    
    def send(self, 
             paths: List[str], 
             callback: Optional[Callable[[int, str, int, int], None]] = None
             ) -> bool:
        """
        Send files using YMODEM protocol.
        
        Args:
            paths: List of file paths to send
            callback: Progress callback function (task_index, name, total, sent)
            
        Returns:
            True if transmission was successful, False otherwise
        """
        # Prepare transmission tasks
        tasks = []
        
        # XMODEM only supports single file transfer
        if self.protocol_type == ProtocolType.XMODEM and len(paths) > 0:
            paths = paths[:1]
            
        # Create tasks for each file
        for path in paths:
            if os.path.isfile(path):
                tasks.append(TransmissionTask(path))
                
        # Process each task
        for task_index, task in enumerate(tasks):
            # Open the file for reading
            try:
                stream = open(task.path, "rb")
            except IOError:
                self.logger.error(f"[Sender]: Cannot open the file: {task.path}, skip.")
                continue
                
            try:
                # Wait for receiver to initiate transfer
                if self.protocol_type == ProtocolType.YMODEM:
                    c = self._read_and_wait([NAK, CRC, G, CAN], 60)
                    
                    if c is None:
                        self.logger.error("[Sender]: Waiting for command from Receiver has timed out, abort and exit!")
                        self._abort()
                        stream.close()
                        return False
                    
                    if c == CAN:
                        self.logger.debug("[Sender]: <- CAN")
                        self.logger.warning("[Sender]: Received a request from the Receiver to cancel the transmission, exit.")
                        stream.close()
                        return True
                        
                    if c == NAK:
                        self.logger.debug("[Sender]: <- NAK")
                        crc = 0  # Use checksum
                    else:
                        self.logger.debug("[Sender]: <- CRC / G")
                        crc = 1  # Use CRC-16
                        
                    # Send file header (filename block)
                    header = self._make_send_header(self._packet_size, 0)
                    self.logger.debug(f"[Sender]: {'SOH' if self._packet_size == 128 else 'STX'} ->")
                    
                    # Prepare filename data
                    data = task.name.encode("utf-8")
                    
                    # Add file length
                    if self._use_length_field:
                        data += bytes(1)  # Null separator
                        data += str(task.total).encode("utf-8")
                        
                    # Add modification date
                    if self._use_date_field:
                        mtime = oct(int(task.mtime))
                        if mtime.startswith("0o"):
                            data += (" " + mtime[2:]).encode("utf-8")
                        else:
                            data += (" " + mtime[1:]).encode("utf-8")
                            
                    # Add file mode
                    if self._use_mode_field:
                        if sys.platform == 'linux':
                            data += (" " + oct(0x8000)).encode("utf-8")
                        else:
                            data += (" 0").encode("utf-8")
                            
                    # Add serial number
                    if self._use_sn_field:
                        data += (" 0").encode("utf-8")
                        
                    # Pad data to packet size
                    data = data.ljust(self._packet_size, b"\x00")
                    checksum = self._make_send_checksum(crc, data)
                    
                    # Send filename block with retries
                    retries = 0
                    while True:
                        if self.protocol_subtype == ProtocolSubType.YMODEM_BATCH_FILE_TRANSMISSION:
                            if retries < 10:
                                self.write(header + data + checksum)
                                self.logger.debug("[Sender]: Filename packet ->")
                                
                                # Wait for ACK
                                c = self._read_and_wait([ACK])
                                if c:
                                    self.logger.debug("[Sender]: <- ACK")
                                    break
                                else:
                                    self.logger.warning("[Sender]: No ACK from Receiver, preparing to retransmit.")
                                    retries += 1
                            else:
                                self.logger.error("[Sender]: The number of retransmissions has reached the maximum limit, abort and exit!")
                                self._abort()
                                stream.close()
                                return False
                        else:  # YMODEM-G
                            self.write(header + data + checksum)
                            self.logger.debug("[Sender]: Filename packet ->")
                            break
                
                # Wait for receiver to request data
                c = self._read_and_wait([NAK, CRC, G, CAN], 60)
                
                if c is None:
                    self.logger.error("[Sender]: Waiting for command from Receiver has timed out, abort and exit!")
                    self._abort()
                    stream.close()
                    return False
                
                if c == CAN:
                    self.logger.debug("[Sender]: <- CAN")
                    self.logger.warning("[Sender]: Received a request from the Receiver to cancel the transmission, exit.")
                    stream.close()
                    return True
                    
                if c == NAK:
                    self.logger.debug("[Sender]: <- NAK")
                    crc = 0  # Use checksum
                else:
                    self.logger.debug("[Sender]: <- CRC / G")
                    crc = 1  # Use CRC-16
                    
                # Send file data
                sequence = 1
                task.success_packet_count = 0
                
                while True:
                    # Read chunk from file
                    data = stream.read(self._packet_size)
                    
                    # End of file
                    if not data:
                        self.logger.debug("[Sender]: Reached EOF")
                        stream.close()
                        break
                        
                    # Prepare header and data
                    header = self._make_send_header(self._packet_size, sequence)
                    self.logger.debug(f"[Sender]: {'SOH' if self._packet_size == 128 else 'STX'} ->")
                    
                    # Fill with padding (^Z)
                    data_length = len(data)
                    data = data.ljust(self._packet_size, b"\x1a")
                    checksum = self._make_send_checksum(crc, data)
                    
                    # Send data block with retries
                    retries = 0
                    while True:
                        if self.protocol_type == ProtocolType.XMODEM or self.protocol_subtype == ProtocolSubType.YMODEM_BATCH_FILE_TRANSMISSION:
                            if retries < 10:
                                self.write(header + data + checksum)
                                self.logger.debug(f"[Sender]: Data packet {sequence} ->")
                                
                                # Wait for ACK
                                c = self._read_and_wait([ACK])
                                if c:
                                    self.logger.debug("[Sender]: <- ACK")
                                    task.sent += data_length
                                    task.success_packet_count += 1
                                    if callable(callback):
                                        callback(task_index, task.name, task.total, task.sent)
                                    break
                                else:
                                    self.logger.warning("[Sender]: No ACK from Receiver, preparing to retransmit.")
                                    retries += 1
                            else:
                                self.logger.error("[Sender]: The number of retransmissions has reached the maximum limit, abort and exit!")
                                self._abort()
                                stream.close()
                                return False
                        else:  # YMODEM-G
                            self.write(header + data + checksum)
                            self.logger.debug(f"[Sender]: Data packet {sequence} ->")
                            task.sent += data_length
                            task.success_packet_count += 1
                            if callable(callback):
                                callback(task_index, task.name, task.total, task.sent)
                            break
                            
                    # Increment sequence number (wraps at 256)
                    sequence = (sequence + 1) % 256
                    
                # Send EOT with retries
                retries = 0
                while True:
                    if retries < 10:
                        c = self._write_and_wait(EOT, [ACK])
                        self.logger.debug("[Sender]: EOT ->")
                        
                        if c:
                            self.logger.debug("[Sender]: <- ACK")
                            break
                        else:
                            self.logger.warning("[Sender]: No ACK from Receiver, preparing to retransmit.")
                            retries += 1
                    else:
                        self.logger.error("[Sender]: The number of retransmissions has reached the maximum limit, abort and exit!")
                        self._abort()
                        return False
            
            except Exception as e:
                self.logger.error(f"[Sender]: Error during file transfer: {e}")
                self._abort()
                if 'stream' in locals() and stream:
                    stream.close()
                return False
                
        # Send batch end (null filename) for YMODEM
        if self.protocol_type == ProtocolType.YMODEM:
            header = self._make_send_header(self._packet_size, 0)
            data = bytearray().ljust(self._packet_size, b"\x00")
            checksum = self._make_send_checksum(crc, data)
            self.write(header + data + checksum)
            self.logger.debug("[Sender]: Batch end packet ->")
            
        return True
    
    def recv(self, 
             path: str, 
             callback: Optional[Callable[[int, str, int, int], None]] = None
             ) -> bool:
        """
        Receive files using YMODEM protocol.
        
        Args:
            path: Directory path to save received files
            callback: Progress callback function (task_index, name, total, sent)
            
        Returns:
            True if reception was successful, False otherwise
        """
        # YMODEM receive implementation
        if self.protocol_type == ProtocolType.YMODEM:
            # Task index
            task_index = -1
            
            while True:
                task = TransmissionTask()
                
                # Send initial 'C' or 'G' to initiate transfer
                for _ in range(10):
                    if self.protocol_subtype == ProtocolSubType.YMODEM_BATCH_FILE_TRANSMISSION:
                        c = self._write_and_wait(CRC, [SOH, STX, CAN], 10)
                        self.logger.debug("[Receiver]: CRC ->")
                    else:  # YMODEM-G
                        c = self._write_and_wait(G, [SOH, STX, CAN], 10)
                        self.logger.debug("[Receiver]: G ->")
                    if c:
                        break
                        
                # Process filename block
                retries = 0
                while True:
                    if c:
                        if c == CAN:
                            self.logger.debug("[Receiver]: <- CAN")
                            self.logger.warning("[Receiver]: Received a request from the Sender to cancel the transmission, exit.")
                            return True
                    else:
                        self.logger.error("[Receiver]: Waiting for response from Sender has timed out, abort and exit!")
                        self._abort()
                        return False
                        
                    # Determine packet size
                    if c == SOH:
                        self.logger.debug("[Receiver]: <- SOH")
                        packet_size = 128
                    else:
                        self.logger.debug("[Receiver]: <- STX")
                        packet_size = 1024
                        
                    # Read sequence numbers
                    seq1 = self.read(1)
                    if seq1:
                        seq1 = ord(seq1)
                        seq2 = self.read(1)
                        if seq2:
                            seq2 = 0xff - ord(seq2)
                    else:
                        seq2 = None
                        
                    received = False
                    
                    # Check for valid sequence (0 for filename block)
                    if seq1 == seq2 == 0:
                        data = self.read(packet_size + 2)  # Data + CRC
                        
                        if data and len(data) == (packet_size + 2):
                            # Verify checksum
                            valid, data = self._verify_recv_checksum(1, data)
                            
                            if valid:
                                # Extract filename
                                file_name = bytes.decode(data.split(b"\x00")[0], "utf-8")
                                
                                # Check for batch end
                                if not file_name:
                                    self.logger.debug("[Receiver]: <- Batch end packet")
                                    if self.protocol_subtype == ProtocolSubType.YMODEM_BATCH_FILE_TRANSMISSION:
                                        self.write(ACK)
                                        self.logger.debug("[Receiver]: ACK ->")
                                    return True
                                    
                                # Process filename block
                                self.logger.debug("[Receiver]: <- Filename packet.")
                                
                                task_index += 1
                                task.name = file_name
                                self.logger.debug(f"[Receiver]: File - {task.name}")
                                
                                # Extract file size if present
                                data = bytes.decode(data.split(b"\x00")[1], "utf-8")
                                
                                if self._use_length_field:
                                    space_index = data.find(" ")
                                    task.total = int(data if space_index == -1 else data[:space_index])
                                    self.logger.debug(f"[Receiver]: Size - {task.total} bytes")
                                    data = data[space_index + 1:] if space_index != -1 else ""
                                    
                                # Extract modification time if present
                                if self._use_date_field and data:
                                    space_index = data.find(" ")
                                    task.mtime = int(data if space_index == -1 else data[:space_index], 8)
                                    self.logger.debug(f"[Receiver]: Mtime - {task.mtime} seconds")
                                    data = data[space_index + 1:] if space_index != -1 else ""
                                    
                                # Extract file mode if present
                                if self._use_mode_field and data:
                                    space_index = data.find(" ")
                                    task.mode = int(data if space_index == -1 else data[:space_index])
                                    self.logger.debug(f"[Receiver]: Mode - {task.mode}")
                                    data = data[space_index + 1:] if space_index != -1 else ""
                                    
                                # Extract serial number if present
                                if self._use_sn_field and data:
                                    space_index = data.find(" ")
                                    task.sn = int(data if space_index == -1 else data[:space_index])
                                    self.logger.debug(f"[Receiver]: SN - {task.sn}")
                                    
                                received = True
                                
                            # Broken packet
                            else:
                                self.logger.warning("[Receiver]: Checksum failed.")
                        
                        # Timeout receiving data
                        else:
                            self.logger.warning("[Receiver]: Received data timed out.")
                            
                    # Invalid header: wrong sequence
                    else:
                        # Skip this packet
                        self.logger.warning("[Receiver]: Wrong sequence, drop the whole packet.")
                        self.read(packet_size + 2)
                        
                    # Handle retransmission or proceed
                    if self.protocol_subtype == ProtocolSubType.YMODEM_BATCH_FILE_TRANSMISSION and not received:
                        if retries < 10:
                            self.logger.warning("[Receiver]: Send a request for retransmission.")
                            self._purge()
                            c = self._write_and_wait(NAK, [SOH, STX, CAN])
                            self.logger.debug("[Receiver]: NAK ->")
                            retries += 1
                        else:
                            self.logger.error("[Receiver]: The number of retransmissions has reached the maximum limit, abort and exit!")
                            self._abort()
                            return False
                    elif self.protocol_subtype == ProtocolSubType.YMODEM_G_FILE_TRANSMISSION and not received:
                        self.logger.error("[Receiver]: An error occurred during the transfer process using YMODEM_G, abort and exit!")
                        self._abort()
                        return False
                    else:
                        # Open file for writing
                        file_path = os.path.join(path, task.name)
                        try:
                            stream = open(file_path, "wb+")
                            if self.protocol_type == ProtocolType.YMODEM:
                                self.write(ACK)
                                self.logger.debug("[Receiver]: ACK ->")
                            break
                        except IOError:
                            self.logger.error(f"[Receiver]: Cannot open the save path: {file_path}, abort and exit!")
                            self._abort()
                            return False
                
                # Send 'C' or 'G' to request data
                for _ in range(10):
                    if self.protocol_type == ProtocolType.XMODEM or self.protocol_subtype == ProtocolSubType.YMODEM_BATCH_FILE_TRANSMISSION:
                        c = self._write_and_wait(CRC, [SOH, STX, CAN, EOT], 10)
                        self.logger.debug("[Receiver]: CRC ->")
                    else:  # YMODEM-G
                        c = self._write_and_wait(G, [SOH, STX, CAN, EOT], 10)
                        self.logger.debug("[Receiver]: G ->")
                    if c:
                        break
                
                # Check if sender canceled
                if c == CAN:
                    self.logger.debug("[Receiver]: <- CAN")
                    self.logger.warning("[Receiver]: Received a request from the Sender to cancel the transmission, exit.")
                    if 'stream' in locals() and stream:
                        stream.close()
                    return True
                
                # If no response in CRC mode, try checksum mode
                if (self.protocol_type == ProtocolType.XMODEM or self.protocol_subtype == ProtocolSubType.YMODEM_BATCH_FILE_TRANSMISSION) and not c:
                    self.logger.warning("[Receiver]: No response in CRC mode, try checksum mode...")
                    for _ in range(10):
                        c = self._write_and_wait(NAK, [SOH, STX, CAN, EOT], 10)
                        if c:
                            if c == CAN:
                                self.logger.debug("[Receiver]: <- CAN")
                                self.logger.warning("[Receiver]: Received a request from the Sender to cancel the transmission, exit.")
                                if 'stream' in locals() and stream:
                                    stream.close()
                                return True
                            else:
                                crc = 0  # Use checksum
                                break
                
                # If still no response, abort
                if not c:
                    self.logger.error("[Receiver]: No response in checksum mode, abort and exit!")
                    self._abort()
                    if 'stream' in locals() and stream:
                        stream.close()
                    return False
                
                # Receive data packets
                retries = 0
                sequence = 1
                task.success_packet_count = 0
                
                while True:
                    if c == SOH:
                        self.logger.debug("[Receiver]: <- SOH")
                        packet_size = 128
                    elif c == STX:
                        self.logger.debug("[Receiver]: <- STX")
                        packet_size = 1024
                    elif c == CAN:
                        self.logger.debug("[Receiver]: <- CAN")
                        if 'stream' in locals() and stream:
                            stream.close()
                        return True
                    elif c == EOT:
                        self.logger.debug("[Receiver]: <- EOT")
                        self.write(ACK)
                        self.logger.debug("[Receiver]: ACK ->")
                        if 'stream' in locals() and stream:
                            stream.close()
                        break
                    
                    # Read sequence numbers
                    seq1 = self.read(1)
                    if seq1:
                        seq1 = ord(seq1)
                        seq2 = self.read(1)
                        if seq2:
                            seq2 = 0xff - ord(seq2)
                    else:
                        seq2 = None
                    
                    # Default no confirm and no forward
                    received = False
                    forward = False
                    
                    # Check sequence number
                    if seq1 == seq2 == sequence:
                        data = self.read(packet_size + 1 + crc)
                        
                        if data and len(data) == (packet_size + 1 + crc):
                            valid, data = self._verify_recv_checksum(crc, data)
                            
                            # Write data to file
                            if valid:
                                self.logger.debug(f"[Receiver]: <- Data packet {sequence}")
                                
                                valid_length = packet_size
                                
                                # Handle last packet (may be shorter)
                                remaining_length = task.total - task.received
                                if remaining_length > 0:
                                    valid_length = min(valid_length, remaining_length)
                                data = data[:valid_length]
                                
                                task.received += len(data)
                                task.success_packet_count += 1
                                
                                try:
                                    stream.write(data)
                                except Exception as e:
                                    self.logger.error(f"[Receiver]: Failed to write data packet {sequence} to file: {e}, abort and exit!")
                                    self._abort()
                                    if 'stream' in locals() and stream:
                                        stream.close()
                                    return False
                                
                                if callable(callback):
                                    callback(task_index, task.name, task.total, task.received)
                                
                                # Confirm and forward
                                received = True
                                forward = True
                            
                            # Broken packet
                            else:
                                self.logger.warning("[Receiver]: Checksum failed.")
                        
                        # Timeout receiving data
                        else:
                            self.logger.warning("[Receiver]: Received data timed out.")
                    
                    # Expired sequence (already received)
                    elif 0 <= seq1 <= task.success_packet_count:
                        self.logger.warning("[Receiver]: Expired sequence, drop the whole packet.")
                        self.read(packet_size + 1 + crc)
                        
                        # Confirm but no forward
                        received = True
                    
                    # Invalid header: wrong sequence
                    else:
                        # Skip this packet
                        self.logger.warning("[Receiver]: Wrong sequence, drop the whole packet.")
                        self.read(packet_size + 1 + crc)
                    
                    # Handle retransmission or proceed
                    if (self.protocol_type == ProtocolType.XMODEM or self.protocol_subtype == ProtocolSubType.YMODEM_BATCH_FILE_TRANSMISSION) and not received:
                        if retries < 10:
                            # Request retransmission
                            self.logger.warning("[Receiver]: Send a request for retransmission.")
                            self._purge()
                            c = self._write_and_wait(NAK, [SOH, STX, CAN, EOT])
                            self.logger.debug("[Receiver]: NAK ->")
                            retries += 1
                        else:
                            self.logger.error("[Receiver]: The number of retransmissions has reached the maximum limit, abort and exit!")
                            self._abort()
                            if 'stream' in locals() and stream:
                                stream.close()
                            return False
                    elif self.protocol_subtype == ProtocolSubType.YMODEM_G_FILE_TRANSMISSION and not received:
                        self.logger.error("[Receiver]: An error occurred during the transfer process using YMODEM_G, abort and exit!")
                        self._abort()
                        if 'stream' in locals() and stream:
                            stream.close()
                        return False
                    else:
                        if forward:
                            sequence = (sequence + 1) % 256
                        if self.protocol_type == ProtocolType.XMODEM or self.protocol_subtype == ProtocolSubType.YMODEM_BATCH_FILE_TRANSMISSION:
                            c = self._write_and_wait(ACK, [SOH, STX, CAN, EOT])
                            self.logger.debug("[Receiver]: ACK ->")
                            retries = 0
                        else:
                            c = self._read_and_wait([SOH, STX, CAN, EOT])
        
        return True
    
    def _abort(self) -> None:
        """
        Abort the transmission by sending CAN characters.
        """
        for _ in range(2):
            self.write(CAN)
    
    def _purge(self) -> None:
        """
        Purge the input buffer by reading until empty.
        """
        while True:
            c = self.read(1)
            if not c:
                break
    
    def _read_and_wait(self, 
                      wait_chars: List[bytes],
                      wait_time: int = 1
                      ) -> Optional[bytes]:
        """
        Read and wait for specific characters.
        
        Args:
            wait_chars: List of characters to wait for
            wait_time: Maximum wait time in seconds
            
        Returns:
            The character found or None if timeout
        """
        start_time = time.time()
        while True:
            t = time.time() - start_time
            if t > wait_time:
                return None
            c = self.read(1)
            if c in wait_chars:
                return c
    
    def _write_and_wait(self, 
                       write_char: bytes, 
                       wait_chars: List[bytes],
                       wait_time: int = 1
                       ) -> Optional[bytes]:
        """
        Write a character and wait for a response.
        
        Args:
            write_char: Character to write
            wait_chars: List of characters to wait for
            wait_time: Maximum wait time in seconds
            
        Returns:
            The character found or None if timeout
        """
        start_time = time.time()
        self.write(write_char)
        while True:
            t = time.time() - start_time
            if t > wait_time:
                return None
            c = self.read(1)
            if c in wait_chars:
                return c
    
    def _make_send_header(self, packet_size: int, sequence: int) -> bytearray:
        """
        Create a packet header.
        
        Args:
            packet_size: Packet size (128 or 1024)
            sequence: Packet sequence number
            
        Returns:
            Header bytes
        """
        _bytes = []
        if packet_size == 128:
            _bytes.append(ord(SOH))
        elif packet_size == 1024:
            _bytes.append(ord(STX))
        _bytes.extend([sequence, 0xff - sequence])
        return bytearray(_bytes)
    
    def _make_send_checksum(self, crc: int, data: bytes) -> bytearray:
        """
        Calculate checksum or CRC for data.
        
        Args:
            crc: Use CRC (1) or checksum (0)
            data: Data to calculate checksum for
            
        Returns:
            Checksum bytes
        """
        _bytes = []
        if crc:
            crc_value = calc_crc16(data)
            _bytes.extend([crc_value >> 8, crc_value & 0xff])
        else:
            checksum = calc_checksum(data)
            _bytes.append(checksum)
        return bytearray(_bytes)
    
    def _verify_recv_checksum(self, crc: int, data: bytes) -> Tuple[bool, bytes]:
        """
        Verify received data checksum.
        
        Args:
            crc: Use CRC (1) or checksum (0)
            data: Data with checksum
            
        Returns:
            Tuple of (valid, data without checksum)
        """
        if crc:
            _checksum = bytearray(data[-2:])
            remote_sum = (_checksum[0] << 8) + _checksum[1]
            data = data[:-2]
            
            local_sum = calc_crc16(data)
            valid = bool(remote_sum == local_sum)
            if not valid:
                self.logger.debug(f"[Receiver]: CRC verification failed. Sender: {remote_sum:04x}, Receiver: {local_sum:04x}.")
        else:
            _checksum = bytearray([data[-1]])
            remote_sum = _checksum[0]
            data = data[:-1]
            
            local_sum = calc_checksum(data)
            valid = remote_sum == local_sum
            if not valid:
                self.logger.debug(f"[Receiver]: Checksum verification failed. Sender: {remote_sum:02x}, Receiver: {local_sum:02x}.")
        return valid, data
