"""Push snapshots into HA; the receiver owns retries and resource cleanup."""
import asyncio
from contextlib import suppress
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from .c14.commands import CommandError
from .c14.receiver import Receiver
from .c14.recording import RawCapture
from .c14.transport import SerialConfig
from .const import DOMAIN, CONF_STALE_AFTER
from .settings import transport_config
from .boost_timer import BoostTimer
from .c14.control_queue import ControlQueue

_LOGGER = logging.getLogger(__name__)


class Aero4Coordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry)
        self.entry = entry
        self.receiver = Receiver(transport_config(entry.data), stale_after=entry.data[CONF_STALE_AFTER],
                                 on_update=self._receive,local_polling=entry.data.get('local_polling',False),
                                 extended_parameters=entry.data.get('extended_parameters',False),solicit_status=True,direct_boost=True,direct_ventilation=True,direct_user_controls=True)
        self.boost_timer = BoostTimer(self.receiver, Store(hass, 1, f'{DOMAIN}.boost_{entry.entry_id}'))
        self.receiver.boost_timer = self.boost_timer
        self.control_queue = ControlQueue(self.receiver)
        self.receiver.control_queue = self.control_queue
        self.data = self.receiver.snapshot()
        self._visible = self._visible_state(self.data)
        self._task = None
        self._clock_task = None
        self._boost_task = None
        self._queue_task = None
        self.capture = None
        self._capture_lock = asyncio.Lock()

    async def async_start_capture(self, duration):
        async with self._capture_lock:
            if self._task is None or self._task.done():
                raise RuntimeError('Receiver is not running')
            if self.capture is not None and self.capture.running:
                raise RuntimeError('Capture already running')
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            name = f'aero4-{stamp}-{uuid4().hex[:8]}.jsonl'
            config = self.receiver.config
            metadata = {'transport':'serial' if isinstance(config,SerialConfig) else 'tcp'}
            if isinstance(config,SerialConfig):
                metadata.update(baud=config.baud,data_bits=8,parity='N',stop_bits=config.stopbits)
            capture = RawCapture(Path(self.hass.config.path(DOMAIN,'captures',name)),
                                 duration=duration,metadata=metadata)
            self.capture = capture
            await self.hass.async_add_executor_job(capture.start)
            self.receiver.observer = capture.submit
            return capture.snapshot()

    async def async_stop_capture(self, reason='manual'):
        async with self._capture_lock:
            self.receiver.observer = None
            if self.capture is None:
                return {'active':False,'state':'not_started'}
            return await self.hass.async_add_executor_job(self.capture.stop,reason)

    @staticmethod
    def _visible_state(snapshot):
        return (snapshot['transport']['connected'], snapshot['bus_online'], snapshot['aero_online'],
            snapshot.get('polling',{}).get('status'),
            tuple(sorted(snapshot.get('schedule_operation', {}).items())),
            tuple(sorted(snapshot.get('command', {}).items())),
            tuple(sorted(snapshot.get('boost_timer', {}).items())),
            repr(snapshot.get('control_queue', {})),
            tuple((key, info['value'], info['status'], info.get('source_key'))
                  for key, info in snapshot['fields'].items()))

    def _receive(self, snapshot):
        visible = self._visible_state(snapshot)
        if visible != self._visible:
            self._visible = visible
            self.async_set_updated_data(snapshot)
        else:
            
            
            self.data = snapshot

    async def _run(self):
        try:
            await self.boost_timer.async_load()
            self._queue_task = self.entry.async_create_background_task(
                self.hass, self.control_queue.async_run(), f'{DOMAIN} control queue')
            self._boost_task = self.entry.async_create_background_task(
                self.hass, self.boost_timer.async_run(), f'{DOMAIN} boost deadline')
            await self.receiver.run()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            
            
            _LOGGER.exception('AERO 4 receiver stopped unexpectedly')
            self.async_set_update_error(error)
        finally:
            if self._boost_task is not None:
                task, self._boost_task = self._boost_task, None
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            if self._queue_task is not None:
                task, self._queue_task = self._queue_task, None
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            try:
                await self.async_stop_capture('receiver_stopped')
            except (OSError,TimeoutError):
                _LOGGER.error('RX capture file did not finish cleanly; receiver has stopped')

    def async_start(self):
        if self._task is not None:
            raise RuntimeError('Coordinator already started')
        self._task = self.entry.async_create_background_task(
            self.hass, self._run(), f'{DOMAIN} receiver')
        if self.entry.data.get('clock_sync', False):
            self._clock_task = self.entry.async_create_background_task(
                self.hass, self._sync_clock_loop(), f'{DOMAIN} clock sync')

    async def async_sync_clock(self):
        return await self.receiver.async_sync_clock(dt_util.now)

    async def _sync_clock_loop(self):
        
        await asyncio.sleep(30)
        while True:
            data = self.receiver.snapshot()
            if (not data['polling']['enabled'] or not data['aero_online']
                    or data['parameter_scan']['known'] != data['parameter_scan']['total']
                    or data['polling']['status'] not in ('ready','polling')
                    or data['command']['status'] in ('queued','waiting')):
                await asyncio.sleep(30)
                continue
            try:
                await self.async_sync_clock()
            except CommandError as error:
                if str(error) not in ('busy', 'control_unavailable'):
                    _LOGGER.warning('Nano clock synchronization was not confirmed: %s', error)
            
            await asyncio.sleep(3600)

    async def async_stop(self):
        if self._boost_task is not None:
            task, self._boost_task = self._boost_task, None
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if self._clock_task is not None:
            task, self._clock_task = self._clock_task, None
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if self._task is not None:
            task, self._task = self._task, None
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
