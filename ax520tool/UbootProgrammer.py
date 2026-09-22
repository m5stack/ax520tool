"""
U-Boot Programmer module for AX520 tool.
Handles firmware operations through U-Boot bootloader over serial port using YMODEM protocol.
"""

import logging
import os
import serial
import tempfile
import time
from typing import Optional, Union, Any
from tqdm import tqdm

from ymodem.Protocol import ProtocolType
from ymodem.Socket import ModemSocket

from .config import ProtocolUboot
from .exceptions import (
    SerialConnectionException,
    HandshakeFailedException,
    CommandFailedException
)

logger = logging.getLogger(__name__)


class TaskProgressBar:
    """Progress bar for tracking YMODEM transfer tasks."""
    
    def __init__(self):
        """Initialize the progress bar."""
        self.last_task_name = ""
        self.last_success = 0
        self.pbar = None

    def show(self, task_index: int, task_name: str, total: int, success: int) -> None:
        """
        Show progress for the current task.
        
        Args:
            task_index: Index of the current task
            task_name: Name of the current task
            total: Total bytes to transfer
            success: Bytes successfully transferred
        """
        if task_name != self.last_task_name:
            if self.last_task_name != "":
                print("\n", end="")
            self.last_task_name = task_name
            self.pbar = tqdm(total=total, unit="B", unit_scale=True, desc="Transferring")

        if self.pbar:
            self.pbar.update(success - self.last_success)
            self.last_success = success
            if success == total:
                self.pbar.close()


class UbootProgrammer:
    """
    U-Boot Programmer for AX520 device.
    
    This class provides firmware programming capabilities through U-Boot bootloader
    using YMODEM protocol for data transfer over serial port.
    """

    def __init__(self, port_name: str, timeout: float = 0.1):
        """
        Initialize the U-Boot programmer.

        Args:
            port_name: Serial port name or serial port object
            timeout: Serial port timeout in seconds
        """
        self.status = "None"
        self.port_name = port_name
        self.timeout = timeout
        self.serial_port = None
        self.handshook = False
        self.boot_mode = None
        self.serial_buff = bytes()

    def open_connection(self) -> bool:
        """
        Open the serial port connection.

        Returns:
            True if connection was opened successfully, False otherwise
            
        Raises:
            SerialConnectionException: If failed to open serial connection
        """
        try:
            if isinstance(self.port_name, str):
                logger.debug(f"Opening serial port {self.port_name}")
                self.serial_port = serial.Serial(
                    self.port_name, 
                    115200, 
                    timeout=self.timeout, 
                    write_timeout=self.timeout
                )
            else:
                logger.debug("Using provided serial object")
                self.serial_port = self.port_name
            return self.serial_port.isOpen()
        except Exception as e:
            logger.error(f"Failed to open serial connection: {e}")
            raise SerialConnectionException(str(e))

    def close_connection(self) -> None:
        """Close the serial port connection."""
        if self.serial_port and self.serial_port.isOpen():
            logger.debug("Closing serial connection")
            self.serial_port.close()
            self.status = "None"

    def _clear_uart(self) -> None:
        """Clear the UART receive buffer."""
        if self.serial_port and self.serial_port.in_waiting > 0:
            self.serial_port.read(self.serial_port.in_waiting)

    def _poll_with_timeout(self, poll_func, timeout: float = 10, interval: float = 0.1) -> bool:
        """
        Poll a function until it returns True or timeout occurs.
        
        Args:
            poll_func: Function to poll
            timeout: Timeout in seconds
            interval: Polling interval in seconds
            
        Returns:
            True if poll_func returned True, False if timeout
        """
        start_time = time.time()
        while True:
            if poll_func():
                return True
            if time.time() - start_time > timeout:
                return False
            time.sleep(interval)

    def _wait_uboot_ready(self) -> bool:
        """
        Wait for U-Boot prompt.
        
        Returns:
            True if U-Boot prompt detected, False otherwise
        """
        self.serial_port.write(b"\r")
        self.serial_port.flush()
        data = self.serial_port.readline()
        if not data.endswith(b"\n"):
            self.serial_buff += data
        else:
            self.serial_buff += data
            serial_str = self.serial_buff.decode("utf-8", errors="ignore").strip()
            print(serial_str)
            self.serial_buff = bytes()
            if ProtocolUboot.UBOOT_FLAGE in serial_str:
                return True
        return False

    def _enter_uboot_hit(self) -> bool:
        """
        Enter U-Boot by hitting any key during autoboot.
        
        Returns:
            True if successfully entered U-Boot, False otherwise
        """
        logger.info("Waiting for U-Boot autoboot")
        self.serial_port.timeout = 1
        self.serial_buff = bytes()
        return self._poll_with_timeout(self._wait_uboot_ready, timeout=120, interval=0.03)

    def _reconfigure_baudrate(self, baudrate: int) -> None:
        """
        Reconfigure serial port baudrate.
        
        Args:
            baudrate: New baudrate to set
        """
        self._clear_uart()
        self.serial_port.close()
        self.serial_port.baudrate = baudrate
        self.serial_port.open()

    def _enter_high_baudrate(self) -> bool:
        """
        Switch to high baudrate for faster communication.
        
        Returns:
            True if successfully switched to high baudrate, False otherwise
        """
        logger.info("Switching to high baudrate")
        self._clear_uart()
        
        if self.serial_port.baudrate != ProtocolUboot.UBOOT_H_BAUDRATE:
            cmd = ProtocolUboot.UBOOT_SET_BAUDRATE.format(ProtocolUboot.UBOOT_H_BAUDRATE)
            self.serial_port.write(cmd.encode('utf-8'))
            self.serial_port.flush()
            
            self._reconfigure_baudrate(ProtocolUboot.UBOOT_H_BAUDRATE)
            
            if not self._poll_with_timeout(self._wait_uboot_ready, timeout=3, interval=0.03):
                self._reconfigure_baudrate(115200)
                return False
        return True

    def _enter_snor(self) -> bool:
        """
        Initialize SPI NOR flash.
        
        Returns:
            True if flash initialized successfully, False otherwise
        """
        logger.info("Initializing SPI NOR flash")
        self._clear_uart()
        self.serial_port.write(ProtocolUboot.UBOOT_DL_PROBE)
        self.serial_port.flush()
        self.serial_port.timeout = 1
        self.serial_buff = bytes()
        
        for i in range(5):
            self.serial_port.write(b"\r")
            self.serial_port.flush()
            data = self.serial_port.readline()
            
            if not data.endswith(b"\n"):
                self.serial_buff += data
            else:
                self.serial_buff += data
                serial_str = self.serial_buff.decode("utf-8", errors="ignore").strip()
                self.serial_buff = bytes()
                if "Failed" in serial_str:
                    logger.error("Failed to initialize SPI NOR flash")
                    return False
            time.sleep(0.03)
            
        return self._poll_with_timeout(self._wait_uboot_ready, timeout=3, interval=0.03)

    def open(self) -> bool:
        """
        Open and initialize U-Boot connection.
        
        Returns:
            True if successfully opened and initialized, False otherwise
        """
        self._clear_uart()
        
        if not self._enter_uboot_hit():
            return False
        if not self._enter_high_baudrate():
            return False
        if not self._enter_snor():
            return False
            
        self.status = "Open"
        logger.debug("U-Boot initialization completed")
        return True

    def handshake(self, timeout: float = 10) -> bool:
        """
        Perform handshake with the device.
        
        Args:
            timeout: Handshake timeout in seconds
            
        Returns:
            True if handshake was successful, False otherwise
            
        Raises:
            HandshakeFailedException: If handshake fails
        """
        logger.info("Starting U-Boot handshake")
        success = self.open()
        if not success:
            raise HandshakeFailedException()
        return success

    def _wait_uboot_loadx_ready(self) -> bool:
        """
        Wait for U-Boot loadx command to be ready.
        
        Returns:
            True if loadx is ready, False otherwise
        """
        data = self.serial_port.read(1)
        return data == b"C"

    def _uboot_loadx(self) -> bool:
        """
        Execute U-Boot loadx command to prepare for XMODEM transfer.
        
        Returns:
            True if loadx command executed successfully, False otherwise
        """
        if self.status != "Open":
            return False
            
        self._clear_uart()
        logger.info("Executing U-Boot loadx command")
        self.serial_port.write(b"loadx ${dl_addr}\r\r")
        self.serial_port.flush()
        self.serial_port.timeout = 0
        
        return self._poll_with_timeout(
            lambda: self.serial_port.read(1) == b"C", 
            timeout=3, 
            interval=0.01
        )
    
    def _align_to_64k(self, size):
        """将输入的数字增长对齐到64K的整数倍"""
        K64 = 65536  # 64K的字节数
        if size <= 0:
            return K64
        return ((size + K64 - 1) // K64) * K64
    
    def _uboot_write_flash(self, address: int, size: int) -> bool:
        """
        Write data from memory buffer to flash.
        
        Args:
            address: Flash address to write to
            size: Size of data to write
            
        Returns:
            True if write successful, False otherwise
        """
        if self.status != "Open":
            return False
            
        self._clear_uart()
        uboot_address = hex(address - 0x3000000)
        uboot_size = hex(self._align_to_64k(size))
        
        cmd = "sf update ${dl_addr} "
        cmd += uboot_address
        cmd += " "
        cmd += uboot_size
        cmd += "\r"

        logger.info(f"Executing U-Boot :{cmd}")
        self.serial_port.write(cmd.encode("utf-8"))
        self.serial_port.flush()
        self.serial_port.timeout = 1
        time.sleep(0.2)
        self._clear_uart()
        return self._poll_with_timeout(self._wait_uboot_ready, timeout=180, interval=0.5)

    def erase(self, address: int, size: int) -> bool:
        """
        Erase a memory region.
        
        Args:
            address: Starting address
            size: Size in bytes
            
        Returns:
            True if erase was successful, False otherwise
            
        Raises:
            CommandFailedException: If erase command fails
        """
        logger.info(f"Erasing memory at {hex(address)}, size: {size}")
        
        if self.status != "Open":
            return False
            
        self._clear_uart()
        uboot_address = hex(address - 0x3000000)
        uboot_size = hex(self._align_to_64k(size))
        
        logger.info(f"Executing: sf erase {uboot_address} {uboot_size}")
        cmd = f"sf erase {uboot_address} {uboot_size}\r"
        self.serial_port.write(cmd.encode("utf-8"))
        self.serial_port.flush()
        time.sleep(0.2)
        self._clear_uart()
        success = self._poll_with_timeout(self._wait_uboot_ready, timeout=240, interval=0.03)
        if not success:
            raise CommandFailedException("ERASE")
        time.sleep(0.2)
        self._clear_uart()
        cmd = ProtocolUboot.UBOOT_ERASE.format(uboot_size)
        logger.info(f"Executing: {cmd}")
        self.serial_port.write(cmd.encode("utf-8"))
        self.serial_port.flush()
        time.sleep(0.2)
        self._clear_uart()
        success = self._poll_with_timeout(self._wait_uboot_ready, timeout=240, interval=0.03)
        if not success:
            raise CommandFailedException("ERASE")
        return success

    def _send(self, data: Union[bytes, bytearray], timeout: Optional[float] = 3) -> Any:
        """
        Send data to the device.
        
        Args:
            data: Data to send
            timeout: Send timeout in seconds
            
        Returns:
            Number of bytes sent
        """
        if self.serial_port:
            self.serial_port.write_timeout = timeout
            return self.serial_port.write(data)
        return 0

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

    def download_firmware(
        self, 
        address: int, 
        firmware_data: bytes, 
        autostart: bool = False
    ) -> bool:
        """
        Download firmware data to the device using YMODEM protocol.
        
        Args:
            address: Starting address for writing to flash
            firmware_data: Firmware data bytes
            autostart: Whether to start the firmware after download
            
        Returns:
            True if download was successful, False otherwise
        """
        logger.info(f"Downloading firmware to {hex(address)}, size: {len(firmware_data)}")
        
        if self.status != "Open":
            return False
            
        self._clear_uart()
        
        # Erase flash region first
        if not self.erase(address, len(firmware_data)):
            return False
            
        # Prepare for XMODEM transfer
        if not self._uboot_loadx():
            return False
            
        try:
            # Create temporary file for YMODEM transfer
            with tempfile.NamedTemporaryFile(mode="wb", delete=False) as temp_file:
                temp_file_path = temp_file.name
                temp_file.write(firmware_data)
                temp_file.flush()

            # Initialize YMODEM client
            modem_cli = ModemSocket(
                self._recv,
                self._send,
                protocol_type=ProtocolType.YMODEM,
                protocol_type_options=[],
                packet_size=128,
            )
            
            logger.debug("Starting YMODEM transfer")
            time.sleep(2)
            
            # Start transfer with progress bar
            progress_bar = TaskProgressBar()
            result = modem_cli.send([temp_file_path], progress_bar.show)
            
            if not result:
                logger.error("YMODEM transfer failed")
                return False
            if not self._poll_with_timeout(self._wait_uboot_ready, timeout=3, interval=0.1):
                logger.error("U-Boot did not respond after YMODEM transfer")
                return False
            logger.info("YMODEM transfer completed successfully")
            
        except Exception as e:
            logger.error(f"Error during firmware download: {e}")
            return False
        finally:
            # Clean up temporary file
            try:
                if 'temp_file_path' in locals():
                    os.unlink(temp_file_path)
            except Exception as e:
                logger.warning(f"Failed to clean up temporary file: {e}")
        
        # Write from memory buffer to flash
        return self._uboot_write_flash(address, len(firmware_data))

    def dump_firmware(self, address: int, length: int) -> Optional[bytes]:
        """
        Read firmware from the device.
        
        Args:
            address: Starting address
            length: Length in bytes
            
        Returns:
            Firmware data as bytes, or None if read failed
        """
        logger.warning("Firmware dump not implemented for U-Boot programmer")
        return None

    def run(self, address: Optional[int] = None) -> bool:
        """
        Run the program.
        
        Args:
            address: Starting address (not used in U-Boot mode)
            
        Returns:
            True if run was successful, False otherwise
        """
        if self.status != "Open":
            return False
            
        self._clear_uart()
        self.serial_port.write(ProtocolUboot.UBOOT_BOOT)
        self.serial_port.flush()
        logger.info("Boot command sent")
        return True

    def reset(self) -> bool:
        """
        Reset the device.
        
        Returns:
            True if reset was successful, False otherwise
        """
        self._clear_uart()
        
        if self.status != "Open":
            return False
            
        self.serial_port.write(ProtocolUboot.UBOOT_RESET)
        self.serial_port.flush()
        self.status = "None"
        logger.info("Reset command sent")
        return True

    def close(self) -> bool:
        """
        Close the programmer connection.
        
        Returns:
            True if close was successful, False otherwise
        """
        return self.reset()

    def exit(self) -> bool:
        """
        Exit the programmer.
        
        Returns:
            True if exit was successful, False otherwise
        """
        return self.reset()
