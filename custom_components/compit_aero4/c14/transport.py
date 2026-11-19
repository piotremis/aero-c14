"""Serial and transparent TCP byte sources.

read() returns bytes, None on a polling timeout, or b'' on TCP EOF.
Operations on one source must be awaited sequentially. Writes are bounded,
single frames; only an explicitly enabled controller calls them.
"""
import asyncio
import math
import os
from dataclasses import dataclass
from typing import Protocol


def positive_seconds(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f'{name} must be finite and positive')


@dataclass(frozen=True)
class SerialConfig:
    port: str
    baud: int = 9600
    stopbits: int = 1
    poll_interval: float = 0.1

    def __post_init__(self):
        if not isinstance(self.port, str) or not self.port.strip() or '://' in self.port:
            raise ValueError('Expected a local serial port path, not a URL')
        if type(self.baud) is not int or self.baud <= 0 or type(self.stopbits) is not int or self.stopbits not in (1, 2):
            raise ValueError('Invalid serial baud or stop bits')
        positive_seconds(self.poll_interval, 'poll_interval')


@dataclass(frozen=True)
class TcpConfig:
    host: str
    port: int
    connect_timeout: float = 10
    poll_interval: float = .05

    def __post_init__(self):
        if not isinstance(self.host, str) or not self.host.strip() or '/' in self.host:
            raise ValueError('Expected a TCP hostname or IP, without a URL scheme')
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError('TCP port must be between 1 and 65535')
        positive_seconds(self.connect_timeout, 'connect_timeout')
        positive_seconds(self.poll_interval, 'poll_interval')


class ByteSource(Protocol):
    async def open(self) -> None: ...
    async def read(self) -> bytes | None: ...
    async def write(self, packet: bytes) -> None: ...
    async def close(self) -> None: ...


async def _offload(function):
    """Do not close a serial handle while its executor operation is unfinished.

    Cancellation waits for the outstanding driver operation, then propagates.
    Reads have a finite timeout. Serial open/close still depend on the OS driver.
    """
    task = asyncio.create_task(asyncio.to_thread(function))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()  
        raise


def _packet(packet):
    if type(packet) is not bytes or len(packet)!=30:
        raise ValueError('Expected one 30-byte packet')


class SerialSource:
    def __init__(self, config: SerialConfig, *, factory=None):
        self.config = config
        self._factory = factory
        self._port = None

    def _open(self):
        factory = self._factory
        if factory is None:
            import serial
            factory = serial.Serial
        options = dict(port=None, baudrate=self.config.baud, bytesize=8, parity='N',
            stopbits=self.config.stopbits, timeout=self.config.poll_interval, write_timeout=.5,
            xonxoff=False, rtscts=False, dsrdtr=False)
        if os.name == 'posix':
            options['exclusive'] = True
        self._port = factory(**options)
        self._port.dtr = False
        self._port.rts = False
        self._port.port = self.config.port
        self._port.open()

    async def open(self):
        if self._port is not None:
            raise RuntimeError('Serial source is already open')
        try:
            await _offload(self._open)
        except BaseException:
            await self.close()
            raise

    async def read(self):
        if self._port is None:
            raise RuntimeError('Serial source is closed')
        
        
        data = await _offload(lambda: self._port.read(min(4096, self._port.in_waiting) or 1))
        return data or None  

    async def close(self):
        if self._port is not None:
            port, self._port = self._port, None
            await _offload(port.close)

    async def write(self, packet):
        _packet(packet)
        if self._port is None:
            raise RuntimeError('Serial source is closed')
        count = await _offload(lambda:self._port.write(packet))
        if count!=len(packet):
            raise OSError('Partial serial packet write; no retry')


class TcpSource:
    def __init__(self, config: TcpConfig):
        self.config = config
        self._reader = self._writer = None

    async def open(self):
        if self._writer is not None:
            raise RuntimeError('TCP source is already open')
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.config.host, self.config.port), self.config.connect_timeout)

    async def read(self):
        if self._reader is None:
            raise RuntimeError('TCP source is closed')
        try:
            return await asyncio.wait_for(self._reader.read(4096), self.config.poll_interval)
        except TimeoutError:
            return None

    async def close(self):
        writer, self._writer, self._reader = self._writer, None, None
        if writer is not None:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 2)
            except (OSError, TimeoutError):
                pass

    async def write(self, packet):
        _packet(packet)
        if self._writer is None:
            raise RuntimeError('TCP source is closed')
        self._writer.write(packet)
        await asyncio.wait_for(self._writer.drain(), .5)


def source_for(config: SerialConfig | TcpConfig) -> ByteSource:
    if isinstance(config, SerialConfig):
        return SerialSource(config)
    if isinstance(config, TcpConfig):
        return TcpSource(config)
    raise TypeError('Expected SerialConfig or TcpConfig')
