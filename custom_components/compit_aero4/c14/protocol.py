"""C14 frame parsing and checksum validation."""
from dataclasses import dataclass

FRAME_SIZE = 30
AIR_QUALITY_FRAME_KEY = 'A9/21/50'

KNOWN_HEADERS = frozenset({
    (0xE4, 0x21), (0xE5, 0x21), (0xE3, 0x44), (0xE3, 0x56),
    (0xE2, 0x44), (0xF0, 0x44), (0xF0, 0x65), (0xF0, 0x72),
    (0xF0, 0x74), (0xF0, 0x77), (0xE4, 0x45),
    (0xA9, 0x21), (0xA9, 0x52), (0xA9, 0x54), (0xA9, 0x57),
    (0xDE, 0x44), (0xDE, 0x56), (0x8B, 0x44), (0x8C, 0x44),
    (0x81, 0x44), (0xAA, 0x44), (0xAA, 0x56), (0xD0, 0x44), (0x96, 0x44),
})


def is_gateway_frame(frame):
    """Call only for checksum-valid frames; sensor telemetry is not a gateway."""
    return frame.key == 'E4/45/70' or (
        frame.key.startswith('A9/') and frame.key != AIR_QUALITY_FRAME_KEY)


def checksum(frame: bytes, k: int) -> int:
    
    if len(frame) != FRAME_SIZE:
        raise ValueError("Expected exactly 30 bytes")
    return (frame[0] + frame[1] + sum(frame[3:29]) + k) & 0xFF


def inferred_k(frame: bytes) -> int:
    return (frame[2] - checksum(frame, 0)) & 0xFF


def checksum_sum7(frame: bytes) -> int:
    return checksum(frame, 0x23) & 0x7F


@dataclass(frozen=True)
class Frame:
    raw: bytes
    offset: int
    first_observed_ns: int | None
    last_observed_ns: int | None
    checksum_valid: bool
    checksum_rule: str = "sum7"

    def __post_init__(self):
        object.__setattr__(self, "raw", bytes(self.raw))
        if len(self.raw) != FRAME_SIZE or self.offset < 0:
            raise ValueError("Invalid frame size or offset")

    @property
    def key(self) -> str:
        return f"{self.raw[0]:02X}/{self.raw[1]:02X}/{self.raw[3]:02X}"

    @property
    def group_key(self) -> str:
        if self.key == "E3/44/29":
            return f"{self.key}:{self.raw[4]:02X}"
        if ((self.raw[0], self.raw[1], self.raw[3]) in {
                (0xA9, 0x52, 0x70), (0xA9, 0x54, 0x70), (0xA9, 0x57, 0x70),
                (0xF0, 0x72, 0x29), (0xF0, 0x74, 0x29), (0xF0, 0x77, 0x29)}):
            addresses = [self.raw[i:i + 2].hex().upper() for i in range(5, 29, 4)
                         if self.raw[i:i + 2] != b'\x00\x00']
            return f"{self.key}@{','.join(addresses)}"
        return self.key


class StreamParser:
    

    def __init__(self, discovery: bool = False, checksum_mode: str = "sum7"):
        if checksum_mode != "sum7":
            raise ValueError("AERO 4 uses checksum mode sum7")
        self.discovery = discovery
        self.buffer = bytearray()
        self.times: list[int | None] = []
        self.offset = 0
        self.discarded_bytes = 0
        self.truncated_bytes = 0
        self.checksum_errors = 0

    def feed(self, data: bytes, observed_ns: int | None = None) -> list[Frame]:
        self.buffer.extend(data)
        self.times.extend([observed_ns] * len(data))
        result = []
        cursor = 0
        while len(self.buffer) - cursor >= FRAME_SIZE:
            raw = bytes(self.buffer[cursor:cursor + FRAME_SIZE])
            if raw[29] != 0x23:
                cursor += 1
                self.discarded_bytes += 1
                continue
            valid = checksum_sum7(raw) == raw[2]
            if valid or self.discovery or (raw[0], raw[1]) in KNOWN_HEADERS:
                result.append(Frame(raw, self.offset + cursor, self.times[cursor],
                                    self.times[cursor + 29], valid))
                if not valid:
                    self.checksum_errors += 1
            if valid:
                cursor += FRAME_SIZE
            else:
                cursor += 1
                self.discarded_bytes += 1
        if cursor:
            del self.buffer[:cursor]
            del self.times[:cursor]
            self.offset += cursor
        return result

    def finish(self):
        """Discard an incomplete tail at EOF/gap; never pad missing bytes."""
        size = len(self.buffer)
        self.truncated_bytes += size
        self.discarded_bytes += size
        self.offset += size
        self.buffer.clear()
        self.times.clear()
