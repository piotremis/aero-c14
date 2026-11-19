"""Bounded RX recording fed by the existing reader, with file I/O off-loop."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import queue
import threading
import time
from .transport import positive_seconds

_RETENTION_LOCK = threading.Lock()


class CaptureQuotaExceeded(OSError):
    """Export/remove old diagnostic captures before creating another."""


class RawCapture:
    def __init__(self, path, *, duration=120, max_bytes=10*1024*1024,
                 queue_size=256, metadata=None):
        positive_seconds(duration, 'duration')
        if duration > 900 or type(max_bytes) is not int or not 2048 <= max_bytes <= 10*1024*1024:
            raise ValueError('Capture duration/size outside limits')
        if type(queue_size) is not int or not 1 <= queue_size <= 4096:
            raise ValueError('Invalid capture queue size')
        self.path = Path(path)
        self.duration, self.max_bytes = duration, max_bytes
        self.metadata = {k:v for k,v in (metadata or {}).items()
                         if k in {'transport','baud','data_bits','parity','stop_bits'}}
        self._queue = queue.Queue(maxsize=queue_size)
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._thread = None
        self._start_ns = self._wall_ns = None
        self._stats = dict(state='not_started', reason=None, rx_chunks=0, rx_bytes=0,
                           tx_packets=0, tx_bytes=0,
                           stream_gaps=0, dropped_chunks=0, dropped_bytes=0,
                           file_bytes=0, sha256=None, error_type=None)

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def snapshot(self):
        with self._lock:
            return {**self._stats, 'active': self.running and not self._stop.is_set(),
                    'filename': self.path.name, 'duration_seconds': self.duration,
                    'max_bytes': self.max_bytes, 'queued_records': self._queue.qsize()}

    def _request_stop(self, reason):
        with self._lock:
            if self._stats['reason'] is None: self._stats['reason'] = reason
        self._stop.set()

    def start(self):
        """Call through an executor; returns only after opening a new file."""
        if self._thread is not None or self._stop.is_set(): raise RuntimeError('Capture already started or stopped')
        self._start_ns, self._wall_ns = time.monotonic_ns(), time.time_ns()
        self._thread = threading.Thread(target=self._run, name='aero4-rx-capture', daemon=True)
        self._thread.start()
        if not self._ready.wait(10):
            self._request_stop('start_timeout')
            raise TimeoutError('Capture file did not open in time')
        if self.snapshot()['state'] == 'failed':
            if self.snapshot()['reason']=='retention_limit': raise CaptureQuotaExceeded('Capture storage quota reached')
            raise OSError('Could not create capture file')

    def submit(self, event):
        """Nonblocking receiver callback. No disk, serialization, or port access."""
        if not self.running or self._stop.is_set(): return False
        observed = event['observed_ns']
        if type(observed) is not int or observed < self._start_ns:
            raise ValueError('Invalid capture observation time')
        if observed - self._start_ns > self.duration*1e9:
            self._request_stop('duration')
            return False
        kind = event['kind']
        if kind not in ('rx','tx','stream_gap'): raise ValueError('Unsupported capture event')
        data = event.get('data', b'')
        if kind in ('rx','tx') and (not isinstance(data, bytes) or len(data) > 4096):
            self._request_stop('invalid_chunk')
            return False
        item = (kind, observed, data, event.get('session', 0), event.get('reason'))
        try:
            self._queue.put_nowait(item)
            return True
        except queue.Full:
            with self._lock:
                self._stats['dropped_chunks'] += int(kind in ('rx','tx'))
                self._stats['dropped_bytes'] += len(data)
            self._request_stop('queue_overflow')
            return False

    def stop(self, reason='manual'):
        """Call through an executor. Never closes the Serial/TCP source."""
        self._request_stop(reason)
        if self._thread is not None:
            self._thread.join(5)
            if self._thread.is_alive(): raise TimeoutError('Capture is still finishing file I/O')
        return self.snapshot()

    def _utc(self, observed):
        wall = self._wall_ns + observed - self._start_ns
        return datetime.fromtimestamp(wall/1e9, timezone.utc).isoformat()

    def _run(self):
        digest = hashlib.sha256()
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with _RETENTION_LOCK:
                files = list(self.path.parent.glob('aero4-*.jsonl'))
                if len(files)>=5 or sum(path.stat().st_size for path in files) + self.max_bytes > 50*1024*1024:
                    raise CaptureQuotaExceeded('Capture storage quota reached')
                fd = os.open(self.path, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'wb') as output:
                def write(row):
                    line = (json.dumps(row, ensure_ascii=False)+'\n').encode('utf-8')
                    output.write(line);output.flush();digest.update(line)
                    with self._lock: self._stats['file_bytes'] += len(line)
                write({'schema':'c14.rx.v3','kind':'session','scenario':'ha_raw_capture',
                    'started_utc':self._utc(self._start_ns), 'duration_seconds':self.duration,
                    'max_bytes':self.max_bytes, 'starts_mid_stream':True,
                    'timestamp_basis':'host RX read / TX write completion, not wire byte timing', **self.metadata})
                with self._lock: self._stats['state'] = 'recording'
                self._ready.set()
                while True:
                    if time.monotonic_ns()-self._start_ns >= self.duration*1e9:
                        self._request_stop('duration')
                    try: item = self._queue.get(timeout=0.05)
                    except queue.Empty:
                        if self._stop.is_set(): break
                        continue
                    kind, observed, data, session, reason = item
                    row = {'kind':kind,'elapsed_ns':max(0,observed-self._start_ns),
                           'utc':self._utc(observed),'session':session}
                    if kind in ('rx','tx'): row['hex'] = data.hex()
                    if kind!='rx': row['reason'] = reason
                    size = len((json.dumps(row,ensure_ascii=False)+'\n').encode('utf-8'))
                    if self._stats['file_bytes'] + size + 1024 > self.max_bytes:
                        with self._lock:
                            self._stats['dropped_chunks'] += int(kind in ('rx','tx'))
                            self._stats['dropped_bytes'] += len(data)
                        self._request_stop('size_limit')
                        
                        break
                    write(row)
                    with self._lock:
                        self._stats['rx_chunks'] += int(kind=='rx')
                        self._stats['rx_bytes'] += len(data) if kind=='rx' else 0
                        self._stats['tx_packets'] += int(kind=='tx')
                        self._stats['tx_bytes'] += len(data) if kind=='tx' else 0
                        self._stats['stream_gaps'] += int(kind=='stream_gap')
                self._discard_queue()
                write({'kind':'capture_end','elapsed_ns':time.monotonic_ns()-self._start_ns,
                       'reason':self._stats['reason'], 'rx_bytes':self._stats['rx_bytes'],
                       'tx_bytes':self._stats['tx_bytes'], 'tx_packets':self._stats['tx_packets'],
                       'dropped_chunks':self._stats['dropped_chunks'],
                       'dropped_bytes':self._stats['dropped_bytes']})
            with self._lock:
                self._stats.update(state='finished',sha256=digest.hexdigest())
        except Exception as error:
            with self._lock:
                self._stats.update(state='failed',reason='retention_limit' if isinstance(error,CaptureQuotaExceeded) else 'io_error',error_type=type(error).__name__)
        finally:
            self._stop.set()
            self._ready.set()
            
            self._discard_queue()

    def _discard_queue(self):
        while True:
            try: kind,_,data,_,_ = self._queue.get_nowait()
            except queue.Empty: break
            with self._lock:
                self._stats['dropped_chunks'] += int(kind in ('rx','tx'))
                self._stats['dropped_bytes'] += len(data)
