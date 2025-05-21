# AX520Tool

## Description

AX520Tool is a versatile command-line tool designed for programming firmware onto AX520 series devices via a serial port. It facilitates various operations such as flashing firmware, reading and verifying memory, erasing flash, and managing device execution. Whether you're a developer or an embedded systems enthusiast, AX520Tool streamlines the process of interacting with AX520-based hardware.

## Features

- **Firmware Downloading:** Upload firmware to AX520 devices with precise memory address targeting.
- **Memory Operations:** Read, write, and erase device memory regions.
- **Firmware Verification:** Ensure the integrity of flashed firmware by comparing device memory with source files.
- **Command-Line Interface:** Intuitive and flexible CLI for executing various operations.
- **Progress Indicators:** Real-time feedback during lengthy operations using progress bars.
- **Error Handling:** Comprehensive exception handling to guide users through issues.
- **Modular Design:** Clean separation of configuration, operations, and CLI interface.
- **Type Annotations:** Improved code readability and IDE support with Python type hints.

## Installation

```bash
pip install ax520tool
```

For development installation:

```bash
git clone https://github.com/m5stack/ax520tool.git
cd ax520tool
pip install -e .
```

## Project Structure

The project has been restructured with a modular design:

- `ax520tool/config.py` - Configuration constants and board definitions
- `ax520tool/exceptions.py` - Custom exception classes
- `ax520tool/board_helper.py` - Board-specific operations and validations
- `ax520tool/programmer.py` - Core programming operations over serial
- `ax520tool/cli.py` - Command-line interface handling

## Usage

AX520Tool is operated via the command line. Below are the instructions to perform various operations.

### Basic Syntax

```bash
ax520tool -p <serial_port> [options] <command> [command_options]
```

- `-p`, `--port`: **(Required)** Specify the serial port connected to the AX520 device (e.g., `COM3` on Windows or `/dev/ttyUSB0` on Linux).
- `-b`, `--board`: **(Optional)** Specify the board name. Defaults to `M5_TimerCamera520_V10`.
- `-r`, `--reboot`: **(Optional)** Reboot the device after flashing.
- `-c`, `--check`: **(Optional)** Verify firmware after flashing.
- `-e`, `--erase-env`: **(Optional)** Erase env partition before any operation.
- `-v`, `--verbose`: **(Optional)** Enable verbose logging for debugging.
- `-u`, `--uboot`: **(Optional)** With uboot tool.

### Commands

#### 1. Write Flash

Download firmware to the device.

**Syntax:**

```bash
ax520tool -p <serial_port> write_flash <address1> <firmware1> [<address2> <firmware2> ...]
```

- `<address>`: Starting memory address (hex `0x...` or decimal).
- `<firmware>`: Path to the firmware binary file.

**Example:**

```bash
ax520tool -p COM3 write_flash 0x3000000 firmware.bin
```

#### 2. Read Flash

Read firmware from the device.

**Syntax:**

```bash
ax520tool -p <serial_port> read_flash <address> <size> <output_file>
```

- `<address>`: Starting memory address.
- `<size>`: Number of bytes to read.
- `<output_file>`: Path to save the read firmware.

**Example:**

```bash
ax520tool -p COM3 read_flash 0x3000000 1048576 read_firmware.bin
```

#### 3. Erase Flash

Erase a region of the device's flash memory.

**Syntax:**

```bash
ax520tool -p <serial_port> erase_flash <address> <size>
```

- `<address>`: Starting memory address.
- `<size>`: Number of bytes to erase.

**Example:**

```bash
ax520tool -p COM3 erase_flash 0x3000000 65536
```

## Examples

### Flashing Firmware

Download `firmware.bin` to address `0x3000000` and reboot the device after flashing:

```bash
ax520tool -p COM3 -r write_flash 0x3000000 firmware.bin
```

### Reading Firmware

Read `1MB` of firmware starting from address `0x3000000` and save it to `read_firmware.bin`:

```bash
ax520tool -p COM3 read_flash 0x3000000 1048576 read_firmware.bin
```

### Erasing Flash Memory

Erase `64KB` of flash memory starting at address `0x3000000`:

```bash
ax520tool -p COM3 erase_flash 0x3000000 65536
```

### Verifying Firmware

After flashing, verify the integrity of the firmware:

```bash
ax520tool -p COM3 -c write_flash 0x3000000 firmware.bin
```

### Flashing Firmware with uboot tool

use uboot tool Download `firmware.bin` to address `0x3000000` and reboot the device after flashing:

```bash
ax520tool -u -p COM3 -r write_flash 0x3000000 firmware.bin
```

**Note:** The `-c` flag enables verification after flashing each file. **It will never check overlapping**.

### Using Partition Names

You can use partition names instead of addresses for supported boards:

```bash
ax520tool -p COM3 write_flash miniboot miniboot.bin uboot uboot.bin
```

## Development

### Adding Support for New Boards

To add support for a new board, update the `BOARD_DEFS` dictionary in `ax520tool/config.py`:

```python
BOARD_DEFS = {
    'YOUR_BOARD_NAME': {
        'flash_size': 0xYOUR_SIZE,
        'flash_start_addr': 0xSTART_ADDR,
        'flash_range': (0xSTART_ADDR, 0xEND_ADDR),
        'partition': {
            'partition1': 0xADDR1,
            'partition2': 0xADDR2,
            # ...
        }
    },
    # ...
}
```

### Using as a Library

You can also use AX520Tool as a library in your Python projects:

```python
from ax520tool import BoardHelper, Programmer

# Initialize board helper
board_helper = BoardHelper('M5_TimerCamera520_V11')

# Initialize programmer
programmer = Programmer(port_name='/dev/ttyUSB0')
programmer.open_connection()
programmer.handshake()

# Download firmware
with open('firmware.bin', 'rb') as f:
    firmware_data = f.read()
    
address = board_helper.number_helper('0x3000000')
programmer.download_firmware(address, firmware_data)

# Close connection
programmer.close_connection()
```

```python
from ax520tool import BoardHelper, UbootProgrammer

# Initialize board helper
board_helper = BoardHelper('M5_TimerCamera520_V11')

# Initialize programmer
programmer = UbootProgrammer(port_name='/dev/ttyUSB0')
programmer.open_connection()
programmer.handshake()

# Download firmware
with open('linux.uimg', 'rb') as f:
    firmware_data = f.read()
    
address = board_helper.number_helper('0x3030000')
programmer.download_firmware(address, firmware_data)

# Close connection
programmer.close_connection()
```

## License

This project is licensed under the GNU General Public License v3 (GPLv3).
