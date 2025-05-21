"""
Exception classes for AX520 tool.
"""

class AX520ToolException(Exception):
    """Base exception class for AX520 tool."""
    def __init__(self, message):
        super().__init__(message)


class InvalidFlashRangeException(AX520ToolException):
    """Exception raised when an address is outside the valid flash range."""
    def __init__(self, value, def_range):
        message = f'Address {value:#010x} is not within valid range of {def_range[0]:#010x}:{def_range[1]:#010x}'
        super().__init__(message)


class InvalidNumberFormatException(AX520ToolException):
    """Exception raised when a number input is not in a valid format."""
    def __init__(self, value):
        message = f'Input \'{value}\' is not a valid number, it needs to be hex, dec or partition name.'
        super().__init__(message)


class FileNotFoundException(AX520ToolException):
    """Exception raised when a firmware file is not found."""
    def __init__(self, value):
        message = f'Firmware file not found at {value}'
        super().__init__(message)


class SerialConnectionException(AX520ToolException):
    """Exception raised when there's an issue with the serial connection."""
    def __init__(self, message):
        super().__init__(f'Serial connection error: {message}')


class HandshakeFailedException(AX520ToolException):
    """Exception raised when handshake with the device fails."""
    def __init__(self):
        super().__init__('Failed to establish handshake with the device')


class CommandFailedException(AX520ToolException):
    """Exception raised when a command fails to execute."""
    def __init__(self, command):
        super().__init__(f'Command {command} failed to execute')
