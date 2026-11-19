"""Encode supported C14 read requests."""
from .protocol import checksum_sum7


def build_read_query(addresses, *, command=0x52):
    """Build a 30-byte, one-to-six-address query in the supported wire format.

Addresses retain their two wire bytes; they are not reinterpreted as
base128 parameter numbers. Bytes with bit7 set are currently unsupported."""
    if type(command) is not int or command not in (0x52, 0x54):
        raise ValueError('Only observed read commands 0x52 and 0x54 are supported')
    if not isinstance(addresses, (tuple, list)) or not 1 <= len(addresses) <= 6:
        raise ValueError('A read query needs one to six addresses')
    for address in addresses:
        if type(address) is not int or not 0 < address <= 0x7F7F or address & 0x8080:
            raise ValueError('Unsupported two-byte wire address')
    if len(set(addresses)) != len(addresses):
        raise ValueError('Duplicate read addresses are not supported')
    raw = bytearray(30)
    raw[0], raw[1], raw[3], raw[29] = 0xA9, command, 0x70, 0x23
    for i, address in enumerate(addresses):
        offset = 5 + 4*i
        raw[offset:offset+2] = address.to_bytes(2, 'big')
    raw[2] = checksum_sum7(raw)
    return bytes(raw)
