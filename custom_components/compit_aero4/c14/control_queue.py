"""One backend worker per receiver; unsent intents coalesce, writes never replay."""
import asyncio
from dataclasses import dataclass
from functools import wraps
import time
import inspect

from .commands import CommandError, VENTILATION_VALUES, ParameterRefreshOperation
from .parameters import PARAMETERS


@dataclass
class Request:
    id: int
    group: str
    value: object
    priority: int
    callback: object
    future: asyncio.Future
    created: float


class ControlQueue:
    LIMIT = 16
    TTL = 60

    def __init__(self, receiver):
        self.receiver = receiver
        self.pending = []
        self.active = None
        self.worker = None
        self.closed = False
        self._next_id = 0
        self._changed = asyncio.Event()
        self.last = None

    def snapshot(self):
        def info(r):
            return {'id': r.id, 'group': r.group, 'value': r.value}
        return {'active': info(self.active) if self.active else None,
                'pending': [info(r) for r in self.pending], 'last': self.last}

    def has_pending(self, group):
        return any(r.group == group for r in self.pending)

    def _publish(self):
        self.receiver._publish()

    async def async_submit(self, group, value, callback, *, priority=10, power_off=False):
        if self.closed:
            raise CommandError('control_unavailable')
        for old in list(self.pending):
            energizing = old.value is True or isinstance(old.value, str) and old.value not in ('off', 'OFF')
            if old.group == group or power_off and old.group in ('boost', 'fireplace', 'power') and energizing:
                self.pending.remove(old)
                old.future.set_exception(CommandError('superseded'))
        if len(self.pending) >= self.LIMIT:
            raise CommandError('busy')
        self._next_id += 1
        future = asyncio.get_running_loop().create_future()
        
        
        future.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)
        request = Request(self._next_id, group, value, priority, callback, future, time.monotonic())
        self.pending.append(request)
        self._changed.set()
        try:
            self._publish()
        except Exception:
            self.pending.remove(request)
            future.cancel()
            raise
        return await asyncio.shield(future)

    def _ready(self):
        r = self.receiver
        command = r.polling.command
        return (r._sequence_task is None or r._sequence_task is r._refresh_task) and (
            r.polling.phase == 'baseline' or r.polling._window_kind == 'read'
            and r.polling.phase != 'draining') and (
            command is None or not command.pending or isinstance(command, ParameterRefreshOperation))

    async def async_run(self):
        self.worker = asyncio.current_task()
        try:
            while True:
                self._changed.clear()
                for request in list(self.pending):
                    if time.monotonic() - request.created > self.TTL:
                        self.pending.remove(request)
                        request.future.set_exception(CommandError('queue_expired'))
                        self._publish()
                if not self.pending:
                    await self._changed.wait()
                    continue
                if not self._ready():
                    
                    await asyncio.sleep(.05)
                    continue
                request = min(self.pending, key=lambda r: (r.priority, r.id))
                self.pending.remove(request)
                self.active = request
                try:
                    self._publish()
                    if time.monotonic() - request.created > self.TTL:
                        raise CommandError('queue_expired')
                    result = await request.callback()
                except asyncio.CancelledError:
                    request.future.set_exception(CommandError('connection_reset'))
                    raise
                except Exception as error:
                    self.last = {'id': request.id, 'status': 'failed', 'error': str(error)}
                    request.future.set_exception(error)
                else:
                    self.last = {'id': request.id, 'status': 'succeeded'}
                    request.future.set_result(result)
                finally:
                    self.active = None
                    self._publish()
        finally:
            self.closed = True
            for request in self.pending:
                request.future.set_exception(CommandError('connection_reset'))
            self.pending.clear()
            self.worker = None


def _metadata(name, args):
    value = args[-1] if args else None
    if name == 'async_user_control':
        action, value = args
        allowed = {'mode': ('manual','schedule','holiday','away'),
                   'gear': ('B1','B2','B3','stopped'), 'boost': ('off','unlimited','15','30','60')}
        if action not in allowed or value not in allowed[action]:
            raise ValueError('Unknown user option')
        group = 'boost' if action == 'boost' else 'ventilation'
    elif name == 'async_set_parameter':
        key, value = args
        PARAMETERS[key].encode(value)
        group = {'fireplace_active':'fireplace','gwc_mode':'gwc','ventilation_enabled':'power',
                 'boost_duration':'boost','holiday_mode':'ventilation','away_mode':'ventilation'}.get(key, 'parameter:'+key)
    elif name == 'async_set_ventilation':
        if value not in VENTILATION_VALUES:
            raise ValueError('Unknown ventilation option')
        group = 'ventilation'
    elif name == 'async_set_led_flag':
        group = 'led:'+str(args[0])+':'+str(args[1])
    else:
        group = {'async_set_boost':'boost','async_set_bypass':'bypass', 'async_set_bypass_mode':'bypass',
                 'async_sync_clock':'clock','async_reset_filter_counter':'filter',
                 'async_set_schedule_period':'schedule'}.get(name, name)
        if name == 'async_set_schedule_period':
            group += ':'+str(args[0])+':'+str(args[1])
            value = list(args)
        elif name == 'async_sync_clock':
            value = 'home_assistant_time'
    stop = group in ('boost','power') and (value is False or value == 'off')
    return group, value, 0 if stop else 20 if group == 'clock' else 10, group == 'power' and value is False


def queued(method):
    signature = inspect.signature(method)
    @wraps(method)
    async def wrapper(self, *args, **kwargs):
        queue = getattr(self, 'control_queue', None)
        if queue is None or asyncio.current_task() is queue.worker:
            return await method(self, *args, **kwargs)
        bound = signature.bind(self, *args, **kwargs)
        ordered = tuple(value for key, value in bound.arguments.items() if key != 'self')
        group, value, priority, power_off = _metadata(method.__name__, ordered)
        return await queue.async_submit(group, value, lambda: method(self, *args, **kwargs),
                                        priority=priority, power_off=power_off)
    return wrapper
