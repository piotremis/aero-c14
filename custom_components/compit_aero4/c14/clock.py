"""C14 v1.21 Z/z codec. No I/O or automatic clock publication."""
from datetime import datetime
from .protocol import checksum_sum7
from .commands import BypassOperation


def build_clock_query(value: datetime | None = None) -> bytes:
    """Read with six unchanged fields, or set the complete local civil time.

    Callers must convert to HA's configured timezone before encoding.
    Seconds and UTC offsets have no representation on this wire command.
    """
    if value is not None and (not isinstance(value, datetime) or not 2000 <= value.year <= 2099):
        raise ValueError('Clock requires a datetime in 2000..2099')
    raw = bytearray(30)
    raw[0], raw[1], raw[3], raw[28], raw[29] = 0xA9, ord('Z'), 0x70, 1, 0x23
    raw[4:10] = (bytes([126]*6) if value is None else
        bytes((value.minute, value.hour, value.weekday(), value.day, value.month, value.year-2000)))
    raw[2] = checksum_sum7(raw)
    return bytes(raw)


def parse_clock_reply(raw: bytes) -> datetime:
    """Validate a reply from Nano 1; return its timezone-free local time."""
    if (len(raw) != 30 or (raw[0], raw[1], raw[3], raw[29]) != (0xF0, ord('z'), 0x29, 0x23)
            or any(b >= 128 for b in raw[1:]) or checksum_sum7(raw) != raw[2]):
        raise ValueError('Invalid clock reply')
    minute, hour, weekday, day, month, year = raw[4:10]
    if not (minute < 60 and hour < 24 and weekday < 7 and year < 100):
        raise ValueError('Invalid clock fields')
    value = datetime(2000+year, month, day, hour, minute)
    if value.weekday() != weekday:
        raise ValueError('Inconsistent clock weekday')
    return value


class ClockSyncOperation(BypassOperation):
    """No success until a separate read and the window close are confirmed."""
    key = 'clock_sync'

    def packet(self):
        self.target = self.enabled().replace(tzinfo=None, second=0, microsecond=0)
        return build_clock_query(self.target)

    def observe(self, values, now):
        pass

    def tick(self, now, *, can_complete=False):
        if not self.pending:
            return
        if now >= self.queued_ns + 60_000_000_000:
            self.fail('clock_sync_timeout', now)
        elif can_complete and self.write_closed and self.confirmations.get('verified'):
            self.status, self.finished_ns = 'succeeded', now

    def snapshot(self):
        return {**super().snapshot(), 'requested': 'home_assistant_time',
                'verified': bool(self.confirmations.get('verified')),
                'target_local_time': getattr(self, 'target', None).isoformat() if hasattr(self, 'target') else None,
                'confirmed_local_time': self.confirmations.get('clock_local_time')}
