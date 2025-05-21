"""
Programmer module for AX520 tool.
Handles communication with the device over serial port.
"""

import logging
import serial
import struct
import time
import math
from typing import Optional, Tuple, List, Union, Any
from tqdm import tqdm

# from .ymodem import ProtocolType, ModemSocket

from ymodem.Protocol import ProtocolType
from ymodem.Socket import ModemSocket


from .config import Protocol
from .config import ProtocolUboot
from .exceptions import (
    SerialConnectionException,
    HandshakeFailedException,
    CommandFailedException
)

logger = logging.getLogger(__name__)


class Programmer:
    """AX520 Programmer for firmware operations over a serial port."""

    def __init__(self, port_name: str, timeout: float = 0.1):
        """
        Initialize the programmer with the specified serial port and timeout.
        
        Args:
            port_name: Serial port name
            timeout: Serial port timeout in seconds
        """
        self.port_name = port_name
        self.timeout = timeout
        self.serial_port = None
        self.handshook = False
        self.boot_mode = None  # To distinguish between HDBOOT and MINIBOOT modes

    def open_connection(self) -> bool:
        """
        Open the serial port connection.
        
        Returns:
            True if connection was opened successfully, False otherwise
        """
        try:
            self.serial_port = serial.Serial(
                port=self.port_name,
                baudrate=115200,
                timeout=self.timeout,
                write_timeout=self.timeout,
            )
            logger.debug(f"Opened serial port {self.port_name}")
            return self.serial_port.isOpen()
        except Exception as e:
            logger.error(f"Error opening serial port: {e}")
            raise SerialConnectionException(str(e))

    def close_connection(self) -> None:
        """Close the serial port connection."""
        if self.serial_port and self.serial_port.isOpen():
            self.serial_port.close()
            self.serial_port = None
            logger.debug("Serial port closed")

    def _send(self, cmd: int, payload: bytes = b'') -> bool:
        """
        Send a command with an optional payload to the device.
        
        Args:
            cmd: Command code
            payload: Optional payload bytes
            
        Returns:
            True if command was sent successfully, False otherwise
        """
        checksum = 0
        if payload:
            for b in payload:
                checksum = (checksum + b) & 0xFF
        data = Protocol.START_BYTE + bytes([cmd]) + bytes([checksum]) + Protocol.END_BYTE + payload
        try:
            self.serial_port.write(data)
            logger.debug(f"Sent command {cmd} with payload length {len(payload)}")
            return True
        except Exception as e:
            logger.error(f"Error sending data: {e}")
            return False

    def _recv(self, expected_cmd: Optional[int] = None, timeout: Optional[float] = None, 
              length: int = 0) -> Union[int, Tuple[int, List[int]], None]:
        """
        Receive a command from the device.
        
        Args:
            expected_cmd: Expected command code (optional)
            timeout: Receive timeout in seconds (optional)
            length: Expected payload length (optional)
            
        Returns:
            Command code if length is 0, or tuple of (command code, payload) if length > 0
            None if timeout or error
        """
        start_time = time.time()
        stack = []
        received_len = 0
        
        while True:
            if timeout and (time.time() - start_time) > timeout:
                logger.debug("Receive timeout")
                return None
                
            c = self.serial_port.read(1)
            if not c:
                continue
                
            if c != Protocol.START_BYTE:
                continue
                
            cmd = self.serial_port.read(1)
            if not cmd:
                continue
            cmd = cmd[0]
            
            checksum = self.serial_port.read(1)
            if not checksum:
                continue
                
            end_byte = self.serial_port.read(1)
            if end_byte != Protocol.END_BYTE:
                continue
                
            if length > 0:
                # Read payload data
                while length - received_len > 0:
                    data = self.serial_port.read(1)
                    if not data:
                        continue
                    stack.append(data[0])
                    received_len += 1
                    
            logger.debug(f"Received command {cmd}")
            
            if expected_cmd and cmd != expected_cmd:
                logger.error(f"Expected command {expected_cmd}, but received {cmd}")
                return None
                
            if length > 0:
                return cmd, stack
            else:
                return cmd

    def handshake(self, timeout: float = 10) -> bool:
        """
        Perform handshake with the device.
        
        Args:
            timeout: Handshake timeout in seconds
            
        Returns:
            True if handshake was successful, False otherwise
        """
        start_time = time.time()
        while not self.handshook and (time.time() - start_time) < timeout:
            ack = self._recv(timeout=1)
            if ack == Protocol.HDBOOT_NOTIFY:
                logger.debug("Received HDBOOT_NOTIFY")
                self.boot_mode = 'HDBOOT'
                self._send(Protocol.DEBUG_CMD)
                ack = self._recv(expected_cmd=Protocol.ACK_OK, timeout=1)
                if ack == Protocol.ACK_OK:
                    logger.info("Handshake successful")
                    self.handshook = True
                    return True
                else:
                    logger.error(f"Unexpected ACK: {ack}")
            elif ack == Protocol.MINIBOOT_NOTIFY:
                logger.debug("Received MINIBOOT_NOTIFY")
                self.boot_mode = 'MINIBOOT'
                self._send(Protocol.DEBUG_CMD)
                # In MINIBOOT mode, the device may not respond to DEBUG_CMD with ACK_OK
                logger.info("Handshake successful in MINIBOOT mode")
                self.handshook = True
                return True
            else:
                logger.info("Waiting for device notify...")
                
        if not self.handshook:
            logger.error("Handshake failed")
            raise HandshakeFailedException()
            
        return False

    def erase(self, address: int, size: int) -> bool:
        """
        Erase a memory region starting at the specified address.
        
        Args:
            address: Starting address
            size: Size in bytes
            
        Returns:
            True if erase was successful, False otherwise
        """
        # The size needs to be divided by 4 as per protocol (size in words)
        payload = struct.pack('>II', address, size // 4)
        if not self._send(Protocol.ERASE_CMD, payload):
            logger.error("Failed to send ERASE command")
            return False
            
        # Erase can take longer, so increase timeout
        ack = self._recv(expected_cmd=Protocol.ACK_OK, timeout=180)
        if ack == Protocol.ACK_OK:
            logger.debug(f"Memory erased at address {address:#010x}, size {size:#010x} bytes")
            return True
        else:
            logger.error("Erase operation failed")
            raise CommandFailedException("ERASE")

    def _calc_crc8(self, data: bytes) -> int:
        """
        Calculate CRC-8 checksum for the given data.
        
        Args:
            data: Data bytes
            
        Returns:
            CRC-8 checksum
        """
        crc = 0
        for byte in data:
            crc ^= byte << 8
            for _ in range(8):
                if (crc & 0x8000):
                    crc ^= (0x1070 << 3)
                crc <<= 1
        return (crc >> 8) & 0xFF

    def _download_chunk(self, address: int, data: bytes) -> bool:
        """
        Download a chunk of data to the specified address.
        
        Args:
            address: Starting address
            data: Data bytes
            
        Returns:
            True if download was successful, False otherwise
        """
        size = len(data)
        # As per protocol, size needs to be specified in words (32-bit words)
        word_count = size // 4
        payload = struct.pack('>II', address, word_count) + data
        if not self._send(Protocol.DLOAD_CMD, payload):
            return False
            
        ack = self._recv(timeout=1)
        if ack == Protocol.ACK_OK:
            logger.debug(f"Chunk downloaded to address {address:#010x}")
            return True
        else:
            logger.error("Failed to download chunk")
            return False

    def execprog(self, address: int, size_with_crc: int) -> bool:
        """
        Execute the program at the specified address with size and CRC.
        
        Args:
            address: Starting address
            size_with_crc: Size with CRC
            
        Returns:
            True if execution was successful, False otherwise
        """
        payload = struct.pack('>II', address, size_with_crc)
        if not self._send(Protocol.EXECPROG_CMD, payload):
            logger.error("Failed to send EXECPROG command")
            return False
            
        ack = self._recv(timeout=1)
        if ack == Protocol.ACK_OK:
            logger.debug("EXECPROG command acknowledged")
            return True
        else:
            logger.error("Failed to execute program")
            return False

    def download_firmware(self, address: int, firmware_data: bytes, autostart: bool = False) -> bool:
        """
        Download firmware data to the device starting at the specified address.
        
        Args:
            address: Starting address
            firmware_data: Firmware data bytes
            autostart: Whether to start the firmware after download
            
        Returns:
            True if download was successful, False otherwise
        """
        # Ensure firmware data is 4-byte aligned
        if len(firmware_data) % 4 != 0:
            padding = b'\xFF' * (4 - len(firmware_data) % 4)
            firmware_data += padding
            logger.debug(f"Firmware data padded with {len(padding)} bytes")

        total_size = len(firmware_data)
        pos = 0
        chunk_size = Protocol.MAX_BUFFER_SIZE
        exec_size = 0
        chk_buf = b""
        page_addr = address
        page_size = Protocol.DEFAULT_PAGE_SIZE

        # Erase the memory region before downloading
        logger.info(f"Erasing memory at address {address:#010x}, size {total_size:#010x} bytes")
        if not self.erase(address, total_size):
            logger.error("Failed to erase memory")
            return False

        logger.debug(f"Starting firmware download to address {address:#010x}")
        with tqdm(total=total_size, unit='B', unit_scale=True, desc='Downloading') as pbar:
            while pos < total_size:
                remaining = total_size - pos
                if remaining < chunk_size:
                    chunk_size = remaining
                
                # Ensure chunk size is 4-byte aligned
                if (chunk_size & 0x03) > 0:
                    chunk_size = chunk_size & 0x00FFFFFC
                    chunk_size += 4

                chunk = firmware_data[pos:pos + chunk_size]

                # Pad chunk if needed
                if chunk_size > len(chunk):
                    chunk += b'\xFF' * (chunk_size - len(chunk))

                if not self._download_chunk(address + pos, chunk):
                    logger.error(f"Firmware download failed at position {pos}")
                    return False

                exec_size += chunk_size
                chk_buf += chunk

                # Handle execprog if needed
                if exec_size >= page_size:
                    crc = self._calc_crc8(chk_buf)
                    size_with_crc = ((crc << 24) & 0xFF000000) + page_size
                    if not self.execprog(page_addr, size_with_crc):
                        logger.error(f"EXECPROG failed at address {page_addr:#010x}")
                        return False
                    chk_buf = b""
                    exec_size -= page_size
                    page_addr += page_size

                pos += chunk_size
                pbar.update(chunk_size)

            # Final execprog if needed
            if exec_size > 0:
                crc = self._calc_crc8(chk_buf)
                size_with_crc = ((crc << 24) & 0xFF000000) + exec_size
                if not self.execprog(page_addr, size_with_crc):
                    logger.error(f"Final EXECPROG failed at address {page_addr:#010x}")
                    return False

        if autostart:
            return self.run(address)

        return True

    def run(self, address: int) -> bool:
        """
        Run the program starting at the specified address.
        
        Args:
            address: Starting address
            
        Returns:
            True if run was successful, False otherwise
        """
        payload = struct.pack('>I', address)
        if not self._send(Protocol.RUN_CMD, payload):
            logger.error("Failed to send RUN command")
            return False
            
        ack = self._recv(timeout=1)
        if ack == Protocol.ACK_OK:
            logger.info("Device started successfully")
            return True
        else:
            logger.error("Failed to start the device")
            return False

    def write_memory(self, address: int, data: int) -> bool:
        """
        Write a double word to a 4-byte aligned address.
        
        Args:
            address: Memory address
            data: Data to write
            
        Returns:
            True if write was successful, False otherwise
        """
        if not isinstance(data, int):
            logger.error("Data must be an integer")
            return False
            
        payload = struct.pack('>II', address, data)
        if not self._send(Protocol.WRITE_CMD, payload):
            logger.error("Failed to send WRITE command")
            return False
            
        ack = self._recv(timeout=1)
        if ack == Protocol.ACK_OK:
            logger.info(f"Memory written at address {address:#010x} with data {data:#010x}")
            return True
        else:
            logger.error("Failed to write memory")
            return False

    def read_memory(self, address: int, size: int) -> Optional[bytes]:
        """
        Read memory content starting from a specific address.
        
        Args:
            address: Starting address
            size: Size in bytes
            
        Returns:
            Memory content as bytes, or None if read failed
        """
        data = b''
        pos = 0
        total_size = size
        chunk_size = Protocol.MAX_BUFFER_SIZE
        
        logger.debug(f"Reading {total_size} bytes from address {address:#010x}")
        while pos < total_size:
            remaining = total_size - pos
            if remaining < chunk_size:
                chunk_size = remaining
                
            # Size must be a multiple of 4
            if chunk_size % 4 != 0:
                chunk_size += (4 - (chunk_size % 4))
                
            word_count = chunk_size // 4
            payload = struct.pack('>II', address + pos, word_count)
            
            if not self._send(Protocol.READ_CMD, payload):
                logger.error("Failed to send READ command")
                return None
            
            try:
                cmd, chunk_data = self._recv(timeout=5, length=chunk_size)
                self._recv(timeout=1)  # Receive ACK
            except Exception as e:
                logger.error(f"Failed to receive data: {e}")
                return None
            
            data += bytes(chunk_data[:remaining])  # Only take the needed bytes
            pos += chunk_size
            
        return data

    def dump_firmware(self, address: int, length: int) -> Optional[bytes]:
        """
        Read firmware from the device.
        
        Args:
            address: Starting address
            length: Length in bytes
            
        Returns:
            Firmware data as bytes, or None if read failed
        """
        # Ensure 4-byte alignment for total size
        total_size = length
        if total_size % 4 != 0:
            total_size += (4 - total_size % 4)
            
        pos = 0
        chunk_size = Protocol.MAX_BUFFER_SIZE
        firmware = b''
        
        logger.info(f"Reading firmware at address {address:#010x} with length {total_size:#010x}")
        with tqdm(total=total_size, unit='B', unit_scale=True, desc='Reading') as pbar:
            while pos < total_size:
                remaining = total_size - pos
                if remaining < chunk_size:
                    chunk_size = remaining
                    
                # Read chunk from device
                read_data = self.read_memory(address + pos, chunk_size)
                if read_data is None:
                    logger.error("Failed to read memory")
                    return None
                    
                firmware += read_data
                pos += len(read_data)
                pbar.update(len(read_data))
                
        logger.info("Firmware read successful")
        return firmware[:length]  # Return only the requested length
    
    def verify_firmware(self, address: int, firmware_data: bytes) -> bool:
        """
        Verify the firmware by reading back from the device and comparing.
        
        Args:
            address: Starting address
            firmware_data: Firmware data to verify against
            
        Returns:
            True if verification was successful, False otherwise
        """
        # Ensure firmware data is 4-byte aligned
        padded_firmware = firmware_data
        if len(firmware_data) % 4 != 0:
            padding = b'\xFF' * (4 - len(firmware_data) % 4)
            padded_firmware += padding
            logger.debug(f"Firmware data padded with {len(padding)} bytes for verification")

        total_size = len(padded_firmware)
        pos = 0
        chunk_size = Protocol.MAX_BUFFER_SIZE
        
        logger.info(f"Verifying firmware at address {address:#010x} with length {total_size:#010x}")
        with tqdm(total=total_size, unit='B', unit_scale=True, desc='Verifying') as pbar:
            while pos < total_size:
                remaining = total_size - pos
                if remaining < chunk_size:
                    chunk_size = remaining
                    
                # Read chunk from device
                read_data = self.read_memory(address + pos, chunk_size)
                if read_data is None:
                    logger.error("Failed to read memory for verification")
                    return False
                    
                # Compare with firmware data
                expected_chunk = padded_firmware[pos:pos + len(read_data)]
                if read_data != expected_chunk:
                    # Find the exact mismatch location
                    for i in range(len(read_data)):
                        if i < len(expected_chunk) and read_data[i] != expected_chunk[i]:
                            mismatch_addr = address + pos + i
                            logger.error(f"Data mismatch at address {mismatch_addr:#010x}: "
                                        f"expected {expected_chunk[i]:02X}, got {read_data[i]:02X}")
                            return False
                    logger.error("Data mismatch found during verification")
                    return False
                    
                pos += len(read_data)
                pbar.update(len(read_data))
                
        logger.info("Firmware verification successful")
        return True
    
    def exit(self) -> bool:
        """
        Exit from the bootloader mode.
        
        Returns:
            True if exit was successful, False otherwise
        """
        if not self._send(Protocol.EXIT_CMD):
            logger.error("Failed to send EXIT command")
            return False
            
        logger.info("Exited from bootloader mode")
        return True


class TaskProgressBar:
    def __init__(self):
        self.last_task_name = ""
        self.last_success = 0

    def show(self, task_index, task_name, total, success):
        if task_name != self.last_task_name:
            if self.last_task_name != "":
                print('\n', end="")
            self.last_task_name = task_name
            self.pbar = tqdm(total=total, unit='B', unit_scale=True, desc='Verifying')

        self.pbar.update(success - self.last_success)
        self.last_success = success
        if success == total:
            self.pbar.close()


class UbootProgrammer:
    """AX520 Uboot Programmer for firmware operations over a serial port."""

    def __init__(self, port_name: str, timeout: float = 0.1):
        """
        Initialize the programmer with the specified serial port and timeout.
        
        Args:
            port_name: Serial port name
            timeout: Serial port timeout in seconds
        """
        self.port_name = port_name
        self.timeout = timeout
        self.serial_port = None
        self.handshook = False
        self.boot_mode = None  # To track the current boot mode state
        # Initialize YMODEM socket with our custom implementation
        self.ymodem_cli = ModemSocket(
            self._recv,
            self._send,
            protocol_type=ProtocolType.YMODEM,
            protocol_type_options=[],
            packet_size=128
        )
        # socket = ModemSocket(read, write, **socket_args)

    def open_connection(self) -> bool:
        """
        Open the serial port connection.
        
        Returns:
            True if connection was opened successfully, False otherwise
        """
        try:
            self.serial_port = serial.Serial(
                port=self.port_name,
                baudrate=115200,
                timeout=self.timeout,
                write_timeout=self.timeout,
            )
            logger.debug(f"Opened serial port {self.port_name}")
            return self.serial_port.isOpen()
        except Exception as e:
            logger.error(f"Error opening serial port: {e}")
            raise SerialConnectionException(str(e))

    def close_connection(self) -> None:
        """Close the serial port connection."""
        if self.serial_port and self.serial_port.isOpen():
            self.serial_port.close()
            self.serial_port = None
            logger.debug("Serial port closed")

    def _send(self, data: Union[bytes, bytearray], timeout: Optional[float] = 3) -> Any:
        """
        Send data to the device.
        
        Args:
            data: Data bytes to send
            timeout: Send timeout in seconds
            
        Returns:
            True if data was sent successfully, False otherwise
        """
        if self.serial_port:
            self.serial_port.write_timeout = timeout
            try:
                self.serial_port.write(data)
                self.serial_port.flush()
                return True
            except Exception as e:
                logger.error(f"Error sending data: {e}")
                return False
        return False

    def _recv(self, size: int, timeout: Optional[float] = 3) -> Any:
        """
        Receive data from the device.
        
        Args:
            size: Number of bytes to receive
            timeout: Receive timeout in seconds
            
        Returns:
            Received data bytes
        """
        if self.serial_port:
            self.serial_port.timeout = timeout
            return self.serial_port.read(size)
        return b''

    def _clear(self):
        while self.serial_port.in_waiting > 0:
            self.serial_port.read(self.serial_port.in_waiting)


    def handshake(self, timeout: float = 10) -> bool:
        """
        Perform handshake with the device in U-Boot mode.
        
        Args:
            timeout: Handshake timeout in seconds
            
        Returns:
            True if handshake was successful, False otherwise
        """
        self._clear()
        self.boot_mode = 'WAIT_HITBOOT'
        start_time = time.time()
        
        while not self.handshook and (time.time() - start_time) < timeout:
            if self.boot_mode == 'WAIT_HITBOOT':
                # Wait for autoboot message
                data = self.serial_port.readline().decode('utf-8', errors='ignore').strip()
                logger.debug(f'serial:{data}')
                if ProtocolUboot.UBOOT_AUTOBOOT_FLAGE in data:
                    logger.info("Detected autoboot message, sending interrupt")
                    self.boot_mode = 'HITBOOT'
                    self._send(ProtocolUboot.UBOOT_AUTOBOOT_HIT)
                else:
                    logger.info("Waiting for autoboot message...")
            
            elif self.boot_mode == 'HITBOOT':
                # Wait for U-Boot prompt
                data = self.serial_port.readline().decode('utf-8', errors='ignore').strip()
                logger.debug(f'serial:{data}')
                if ProtocolUboot.UBOOT_FLAGE in data:
                    logger.info("Detected U-Boot prompt, setting baudrate")
                    self.boot_mode = 'SET_BAUDRATE'
                    self._send(ProtocolUboot.UBOOT_SET_BAUDRATE.format(ProtocolUboot.UBOOT_H_BAUDRATE).encode('utf-8'))
                else:
                    # Keep sending interrupt in case it was missed
                    self._send(ProtocolUboot.UBOOT_AUTOBOOT_HIT)
                    logger.info("Waiting for U-Boot prompt...")
            
            elif self.boot_mode == 'SET_BAUDRATE':
                # Wait for baudrate change confirmation
                data = self.serial_port.readline().decode('utf-8', errors='ignore').strip()
                logger.debug(f'serial:{data}')
                if ProtocolUboot.UBOOT_SET_BAUDRATE_FLAGE in data:
                    logger.info("Baudrate change requested, reconfiguring serial port")
                    # Close and reopen with higher baudrate
                    self.serial_port.close()
                    self.serial_port.baudrate = ProtocolUboot.UBOOT_H_BAUDRATE
                    self.serial_port.open()
                    self._send(ProtocolUboot.UBOOT_AUTOBOOT_HIT)
                    self.boot_mode = 'WAIT_H_BAUDRATE'
                else:
                    logger.info("Waiting for baudrate change confirmation...")
            
            elif self.boot_mode == 'WAIT_H_BAUDRATE':
                # Wait for U-Boot prompt at new baudrate
                data = self.serial_port.readline().decode('utf-8', errors='ignore').strip()
                logger.debug(f'serial:{data}')
                if ProtocolUboot.UBOOT_FLAGE in data:
                    logger.info("Detected U-Boot prompt at high baudrate, initializing flash")
                    self.boot_mode = 'UBOOT_DL'
                    self._send(ProtocolUboot.UBOOT_DL_PROBE)
                else:
                    self._send(ProtocolUboot.UBOOT_AUTOBOOT_HIT)
                    logger.info("Waiting for U-Boot prompt at high baudrate...")
            
            elif self.boot_mode == 'UBOOT_DL':
                # Wait for flash initialization confirmation
                data = self.serial_port.readline().decode('utf-8', errors='ignore').strip()
                logger.debug(f'serial:{data}')
                if ProtocolUboot.UBOOT_FLAGE in data:
                    logger.info("Flash initialized, handshake successful")
                    self.boot_mode = 'UBOOT'
                    self.handshook = True
                    return True
                else:
                    logger.info("Waiting for flash initialization confirmation...")

        if not self.handshook:
            logger.error("Handshake failed")
            raise HandshakeFailedException()
            
        return False

    def erase(self, address: int, size: int) -> bool:
        """
        Erase a memory region in U-Boot mode.
        
        Args:
            address: Starting address (not used in U-Boot mode, memory buffer is used instead)
            size: Size in bytes
            
        Returns:
            True if erase was successful, False otherwise
        """
        logger.info(f"Erasing memory buffer for size {size} bytes")
        self._clear()
        # Send erase command to fill memory buffer with 0xFF
        if not self._send(ProtocolUboot.UBOOT_ERASE.format(hex(size)).encode('utf-8')):
            logger.error("Failed to send erase command")
            return False
        
        # Wait for command completion
        while True:
            data = self.serial_port.readline().decode('utf-8', errors='ignore').strip()
            logger.debug(f'serial:{data}')
            if ProtocolUboot.UBOOT_FLAGE in data:
                logger.info(f"Memory buffer erased for size {size} bytes")
                return True
            elif "Error" in data or "error" in data:
                logger.error(f"Erase operation failed: {data}")
                raise CommandFailedException("ERASE")
        
        return False

    def download_firmware(self, address: int, firmware_data: bytes, autostart: bool = False) -> bool:
        """
        Download firmware data to the device using YMODEM protocol in U-Boot mode.
        
        Args:
            address: Starting address for writing to flash
            firmware_data: Firmware data bytes
            autostart: Whether to start the firmware after download
            
        Returns:
            True if download was successful, False otherwise
        """
        logger.info(f"Starting firmware download, size: {len(firmware_data)} bytes")

        # First erase the memory buffer
        if not self.erase(0, len(firmware_data)):
            logger.error("Failed to erase memory buffer")
            return False
        self._clear()
        # Send command to receive file via YMODEM
        self._send(ProtocolUboot.UBOOT_REACEIVE)
        
        # Wait for YMODEM receive confirmation ('C' character)
        start_time = time.time()
        ymodem_ready = False
        
        while not ymodem_ready and (time.time() - start_time) < 60:
            # data = self.serial_port.readline().decode('utf-8', errors='ignore').strip()
            data = self._recv(1, 30).decode('utf-8', errors='ignore').strip()
            logger.debug(f'serial:{data}')
            if ProtocolUboot.UBOOT_REACEIVE_FLAGE in data:
                logger.info("YMODEM transfer ready")
                ymodem_ready = True
                break
        
        if not ymodem_ready:
            logger.error("YMODEM transfer not ready")
            return False
        
        # Create a temporary file for YMODEM transfer
        import tempfile
        import os
        try:
            with tempfile.NamedTemporaryFile(mode='wb', delete=False) as temp_file:
                temp_file_path = temp_file.name
                temp_file.write(firmware_data)
                temp_file.flush()
            
            # Create progress bar for YMODEM transfer
            progress_bar = TaskProgressBar()
            self._clear()
            # Start YMODEM transfer
            logger.debug(f"Starting YMODEM transfer from temporary file: {temp_file_path}")
            result = self.ymodem_cli.send([temp_file_path], progress_bar.show)
            # Clean up temporary file
            os.unlink(temp_file_path)
            
            if not result:
                logger.error("YMODEM transfer failed")
                return False
                
            logger.info("YMODEM transfer completed successfully")
            
            # Wait for U-Boot prompt after transfer
            start_time = time.time()
            while (time.time() - start_time) < 30:
                data = self.serial_port.readline().decode('utf-8', errors='ignore').strip()
                if ProtocolUboot.UBOOT_FLAGE in data:
                    break
            self._clear()
            write_cmd_ready = False
            # Write firmware from memory buffer to flash
            write_cmd = ProtocolUboot.UBOOT_WRITE.format(hex(address - 0x3000000), hex(len(firmware_data))).encode('utf-8')
            if not self._send(write_cmd):
                logger.error("Failed to send write command")
                return False
            
            # Wait for write completion
            start_time = time.time()
            while (time.time() - start_time) < 60:
                data = self._recv(128).decode('utf-8', errors='ignore')
                logger.debug(f'serial:{data}')
                if ProtocolUboot.UBOOT_FLAGE in data:
                    logger.info(f"Firmware written to flash at address {address:#010x}")
                    write_cmd_ready = True
                    break
                elif "Error" in data or "error" in data:
                    logger.error(f"Write operation failed: {data}")
                    return False
                self._send(ProtocolUboot.UBOOT_AUTOBOOT_HIT)
                time.sleep(1)
            if not write_cmd_ready:
                logger.error("Write operation timed out")
                return False
            
        except Exception as e:
            logger.error(f"Error during firmware download: {e}")
            return False
            
        finally:
            # Try to clean up temporary file if it still exists
            try:
                if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
            except Exception as e:
                logger.warning(f"Failed to clean up temporary file: {e}")
        if autostart:
            self.run()
        return write_cmd_ready
        
    def write_memory(self, address: int, data: int) -> bool:
        return False
        """
        Write data to memory in U-Boot mode.
        
        Args:
            address: Memory address
            data: Data to write
            
        Returns:
            True if write was successful, False otherwise
        """
        if not isinstance(data, int):
            logger.error("Data must be an integer")
            return False
            
        # Format the command to write memory in U-Boot
        if not self._send(ProtocolUboot.UBOOT_MEM_WRITE.format(hex(address), hex(data), "0x1").encode('utf-8')):
            logger.error("Failed to send memory write command")
            return False
            
        # Wait for command completion
        start_time = time.time()
        while (time.time() - start_time) < 5:
            data = self.serial_port.readline().decode('utf-8', errors='ignore').strip()
            if ProtocolUboot.UBOOT_FLAGE in data:
                logger.info(f"Memory written at address {address:#010x}")
                return True
            elif "Error" in data or "error" in data:
                logger.error(f"Memory write failed: {data}")
                return False
                
        logger.error("Memory write timed out")
        return False
        
    def read_memory(self, address: int, size: int) -> Optional[bytes]:
        return False
        """
        Read memory content in U-Boot mode.
        
        Args:
            address: Starting address
            size: Size in bytes
            
        Returns:
            Memory content as bytes, or None if read failed
        """
        # U-Boot memory display command (md)
        # Format: md.b <address> <count>
        word_count = (size + 3) // 4  # Round up to nearest word
        cmd = ProtocolUboot.UBOOT_MEM_READ.format(hex(address), hex(size)).encode('utf-8')
        
        if not self._send(cmd):
            logger.error("Failed to send memory read command")
            return None
            
        # Parse the memory dump output
        memory_data = bytearray()
        start_time = time.time()
        parsing = False
        
        while (time.time() - start_time) < 10:
            line = self.serial_port.readline().decode('utf-8', errors='ignore').strip()
            
            if ProtocolUboot.UBOOT_FLAGE in line:
                # End of output
                break
                
            if parsing:
                # Parse hex values from the line
                try:
                    parts = line.split(':')
                    if len(parts) >= 2:
                        hex_part = parts[1].strip()
                        hex_values = hex_part.split()
                        for hex_val in hex_values:
                            if len(hex_val) == 2:  # Ensure it's a byte
                                memory_data.append(int(hex_val, 16))
                except Exception as e:
                    logger.error(f"Error parsing memory data: {e}")
                    continue
            
            # Start parsing after seeing the address
            if f"{address:08x}" in line.lower():
                parsing = True
                
        if len(memory_data) >= size:
            return bytes(memory_data[:size])
        else:
            logger.error(f"Incomplete memory read: got {len(memory_data)} bytes, expected {size}")
            return None
            
    def dump_firmware(self, address: int, length: int) -> Optional[bytes]:
        return False
        """
        Read firmware from the device in U-Boot mode.
        
        Args:
            address: Starting address
            length: Length in bytes
            
        Returns:
            Firmware data as bytes, or None if read failed
        """
        logger.info(f"Reading firmware at address {address:#010x} with length {length:#010x}")
        
        # In U-Boot mode, we need to read in smaller chunks
        chunk_size = 256  # Smaller chunk size for U-Boot
        pos = 0
        firmware = bytearray()
        
        with tqdm(total=length, unit='B', unit_scale=True, desc='Reading') as pbar:
            while pos < length:
                remaining = length - pos
                current_chunk = min(remaining, chunk_size)
                
                # Read chunk from device
                read_data = self.read_memory(address + pos, current_chunk)
                if read_data is None:
                    logger.error(f"Failed to read memory at address {address + pos:#010x}")
                    return None
                    
                firmware.extend(read_data)
                pos += len(read_data)
                pbar.update(len(read_data))
                
        logger.info("Firmware read successful")
        return bytes(firmware)
        
    def verify_firmware(self, address: int, firmware_data: bytes) -> bool:
        return False
        """
        Verify the firmware by reading back from the device and comparing.
        
        Args:
            address: Starting address
            firmware_data: Firmware data to verify against
            
        Returns:
            True if verification was successful, False otherwise
        """
        logger.info(f"Verifying firmware at address {address:#010x} with length {len(firmware_data):#010x}")
        
        # In U-Boot mode, verification is done by reading back and comparing
        chunk_size = 256  # Smaller chunk size for U-Boot
        pos = 0
        total_size = len(firmware_data)
        
        with tqdm(total=total_size, unit='B', unit_scale=True, desc='Verifying') as pbar:
            while pos < total_size:
                remaining = total_size - pos
                current_chunk = min(remaining, chunk_size)
                
                # Read chunk from device
                read_data = self.read_memory(address + pos, current_chunk)
                if read_data is None:
                    logger.error(f"Failed to read memory at address {address + pos:#010x}")
                    return False
                    
                # Compare with firmware data
                expected_chunk = firmware_data[pos:pos + current_chunk]
                if read_data != expected_chunk:
                    # Find the exact mismatch location
                    for i in range(len(read_data)):
                        if i < len(expected_chunk) and read_data[i] != expected_chunk[i]:
                            mismatch_addr = address + pos + i
                            logger.error(f"Data mismatch at address {mismatch_addr:#010x}: "
                                        f"expected {expected_chunk[i]:02X}, got {read_data[i]:02X}")
                            return False
                    logger.error("Data mismatch found during verification")
                    return False
                    
                pos += current_chunk
                pbar.update(current_chunk)
                
        logger.info("Firmware verification successful")
        return True
        
    def run(self, address: int) -> bool:
        """
        Run the program starting at the specified address in U-Boot mode.
        
        Args:
            address: Starting address
            
        Returns:
            True if run was successful, False otherwise
        """
        # Format the command to go to the address in U-Boot
        
        if not self._send(ProtocolUboot.UBOOT_BOOT):
            logger.error("Failed to send run command")
            return False
            
        # Wait for command to be acknowledged
        start_time = time.time()
        while (time.time() - start_time) < 5:
            data = self.serial_port.readline().decode('utf-8', errors='ignore').strip()
            if "## Booting kernel" in data:
                logger.info(f"Program started at address {address:#010x}")
                return True
            elif "Error" in data or "error" in data:
                logger.error(f"Run command failed: {data}")
                return False
                
        logger.warning("No explicit confirmation of program start, assuming success")
        return True
        
    def exit(self) -> bool:
        """
        Exit from U-Boot mode.
        
        Returns:
            True if exit was successful, False otherwise
        """
        # In U-Boot, we can use the reset command to exit
        cmd = "reset\r\n".encode('utf-8')
        
        if not self._send(cmd):
            logger.error("Failed to send reset command")
            return False
            
        logger.info("Reset command sent to exit U-Boot")
        return True
