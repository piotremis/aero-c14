"""Backend-owned boost deadline; persisted intent never replays an ON command."""
import asyncio
from contextlib import asynccontextmanager
import logging
import math
import time

from .c14.commands import CommandError
from .c14.parameters import PARAMETERS

_LOGGER = logging.getLogger(__name__)


class BoostTimer:
    def __init__(self, receiver, store, *, clock=time.time):
        self.receiver, self.store, self.clock = receiver, store, clock
        self.deadline = None
        self.minutes = None
        self.phase = 'idle'
        self.error = None
        self._armed_ns = None

    def snapshot(self):
        return {'deadline': self.deadline, 'minutes': self.minutes,
                'status': self.phase, 'error': self.error}

    async def async_load(self):
        saved = await self.store.async_load()
        if not saved:
            return
        deadline = saved.get('deadline')
        minutes = saved.get('minutes')
        if (type(deadline) not in (int, float) or not math.isfinite(deadline)
                or type(minutes) not in (int, float) or not math.isfinite(minutes)
                or minutes <= 0):
            return
        self.deadline, self.minutes = deadline, minutes
        self.phase = saved.get('status', 'running')
        if self.phase not in ('starting', 'running', 'stopping', 'error'):
            self.phase = 'running'
        self.error = saved.get('error')
        self._armed_ns = self.receiver._clock()

    async def _save(self):
        await self.store.async_save(self.snapshot())
        self.receiver._publish()

    async def _clear(self):
        self.deadline = self.minutes = self._armed_ns = None
        self.phase, self.error = 'idle', None
        await self._save()

    @asynccontextmanager
    async def _sequence(self):
        r = self.receiver
        r._check_sequence()
        r.polling._check_request()
        previous, r._sequence_task = r._sequence_task, asyncio.current_task()
        try:
            yield
        finally:
            r._sequence_task = previous

    def _value(self, key):
        info = self.receiver.snapshot()['fields']['parameter_' + key]
        if info['status'] != 'known':
            raise CommandError('control_unavailable')
        return info['value']

    async def async_select(self, value):
        if value == 'off':
            return await self.async_stop()
        minutes = 0 if value == 'unlimited' else int(value)
        PARAMETERS['boost_duration'].encode(minutes)
        async with self._sequence():
            active, duration = self._value('boost'), self._value('boost_duration')
            if (active is True and duration == minutes
                    and (minutes == 0 and self.deadline is None or self.deadline is not None
                         and self.minutes == minutes and self.phase == 'running')):
                return None
            if duration != minutes:
                await self.receiver._async_set_parameter('boost_duration', minutes)
            if minutes:
                
                self.deadline, self.minutes = self.clock() + minutes * 60, minutes
                self.phase, self.error = 'starting', None
                await self._save()
            else:
                await self._clear()
            result = None
            if active is not True:
                result = await self.receiver._async_set_boost(True)
            if minutes:
                self.deadline = self.clock() + minutes * 60
                self._armed_ns = self.receiver._clock()
                self.phase = 'running'
                await self._save()
            return result

    async def async_set_enabled(self, enabled):
        if type(enabled) is not bool:
            raise ValueError('Boost requires a boolean')
        if not enabled:
            return await self.async_stop()
        minutes = self._value('boost_duration')
        return await self.async_select('unlimited' if minutes == 0 else str(int(minutes)))

    async def async_set_duration(self, minutes):
        PARAMETERS['boost_duration'].encode(minutes)
        async with self._sequence():
            result = await self.receiver._async_set_parameter('boost_duration', minutes)
            if self.deadline is not None:
                if minutes == 0:
                    await self._clear()
                else:
                    self.deadline, self.minutes = self.clock() + minutes * 60, minutes
                    self._armed_ns = self.receiver._clock()
                    self.phase, self.error = 'running', None
                    await self._save()
            return result

    async def async_stop(self):
        async with self._sequence():
            result = None
            
            
            fields = self.receiver.snapshot()['fields']
            off = all(fields[k]['status'] == 'known' and fields[k]['value'] is False
                      for k in ('parameter_boost', 'boost_requested', 'boost_active'))
            if not off:
                result = await self.receiver._async_set_boost(False)
            if self._value('boost_duration') != 0:
                await self.receiver._async_set_parameter('boost_duration', 0)
            await self._clear()
            return result

    async def async_tick(self):
        if self.deadline is None or self.phase == 'error':
            return
        r = self.receiver
        queue = getattr(r, 'control_queue', None)
        snapshot = r.snapshot()
        if (not snapshot['transport']['connected'] or not snapshot['aero_online']
                or snapshot['polling']['status'] not in ('ready', 'polling')
                or queue is None and (r._sequence_task is not None
                                      or snapshot['command']['status'] in ('queued', 'waiting'))):
            return
        fields = snapshot['fields']
        manual_off = self.phase == 'running' and self._armed_ns is not None and all(
            fields[k]['status'] == 'known' and fields[k]['value'] is False
            and fields[k]['observed_ns'] is not None
            and fields[k]['observed_ns'] > self._armed_ns
            for k in ('parameter_boost', 'boost_requested', 'boost_active'))
        if self.phase != 'stopping' and not manual_off and self.clock() < self.deadline:
            return
        try:
            if queue is not None and asyncio.current_task() is not queue.worker:
                if queue.has_pending('boost'):
                    return
                deadline = self.deadline
                await queue.async_submit('boost', 'off', lambda: self._async_expire(deadline), priority=0)
            else:
                await self._async_expire(self.deadline)
        except CommandError as error:
            if str(error) in ('busy', 'control_unavailable', 'connection_reset', 'superseded'):
                return
            
            self.phase, self.error = 'error', str(error)
            await self._save()
            _LOGGER.error('Timed boost shutdown was not confirmed: %s', error)

    async def _async_expire(self, deadline):
        async with self._sequence():
            queue = getattr(self.receiver, 'control_queue', None)
            if self.deadline != deadline or queue is not None and queue.has_pending('boost'):
                return
            self.phase = 'stopping'
            await self._save()
            await self.async_stop()

    async def async_run(self):
        while True:
            await self.async_tick()
            await asyncio.sleep(1)
