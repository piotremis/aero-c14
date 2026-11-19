"""Register the bundled cards as Lovelace module resources."""
import asyncio
import hashlib
import logging
from pathlib import Path
from urllib.parse import urlsplit

from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.resources import ResourceStorageCollection, ResourceYAMLCollection
from homeassistant.const import EVENT_CALL_SERVICE, EVENT_COMPONENT_LOADED, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import callback

_LOGGER = logging.getLogger(__name__)
_CARDS = ('aero4-card.js', 'aero4-schedule-card.js')
_LEGACY_LOADER = '/compit_aero4/aero4-loader.js'
_MANAGER = 'compit_aero4_lovelace_resources'


def _resource_path(item):
    try:
        parts = urlsplit(item.get('url', ''))
    except (TypeError, ValueError):
        return None
    return parts.path if not parts.scheme and not parts.netloc else None


class CardResources:
    def __init__(self, hass):
        self.hass = hass
        self._lock = asyncio.Lock()
        self._static_registered = False
        self._yaml_collection = None
        self._closed = False
        self._tasks = set()
        self._unsubscribers = [
            hass.bus.async_listen(EVENT_COMPONENT_LOADED, self._component_loaded),
            hass.bus.async_listen(EVENT_CALL_SERVICE, self._service_called),
            hass.bus.async_listen(EVENT_HOMEASSISTANT_STOP, self.async_close),
        ]

    @callback
    def _component_loaded(self, event):
        if event.data.get('component') in ('frontend', 'lovelace'):
            self._schedule(self.async_register())

    @callback
    def _service_called(self, event):
        if event.data.get('domain') != 'lovelace' or event.data.get('service') != 'reload_resources':
            return
        data = self.hass.data.get(LOVELACE_DATA)
        if data is not None and isinstance(data.resources, ResourceYAMLCollection):
            previous = self._yaml_collection or data.resources
            self._schedule(self._after_yaml_reload(previous), background=True)

    @callback
    def _schedule(self, coroutine, *, background=False):
        if self._closed:
            coroutine.close()
            return
        create = self.hass.async_create_background_task if background else self.hass.async_create_task
        task = create(coroutine, 'AERO C14 Lovelace resources')
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _after_yaml_reload(self, previous):
        for _ in range(600):
            data = self.hass.data.get(LOVELACE_DATA)
            if data is not None and data.resources is not previous:
                await self.async_register()
                return
            await asyncio.sleep(0.05)
        _LOGGER.debug('Lovelace resource reload did not replace the YAML collection')

    @callback
    def async_close(self, event=None):
        self._closed = True
        while self._unsubscribers:
            self._unsubscribers.pop()()
        for task in tuple(self._tasks):
            task.cancel()

    @staticmethod
    def _assets():
        folder = Path(__file__).parent / 'frontend'
        paths = [folder / name for name in (*_CARDS, 'aero4-loader.js')]
        desired = {
            '/compit_aero4/'+name: {
                'url': '/compit_aero4/'+name+'?v='+hashlib.sha256((folder/name).read_bytes()).hexdigest()[:12],
                'type': 'module',
            }
            for name in _CARDS
        }
        return paths, desired

    async def async_register(self):
        async with self._lock:
            if self._closed or 'frontend' not in self.hass.config.components:
                return
            try:
                paths, desired = await self.hass.async_add_executor_job(self._assets)
                if not self._static_registered:
                    await self.hass.http.async_register_static_paths([
                        StaticPathConfig('/compit_aero4/'+path.name, str(path), False)
                        for path in paths
                    ])
                    self._static_registered = True
                data = self.hass.data.get(LOVELACE_DATA)
                if data is None:
                    return
                collection = data.resources
                if isinstance(collection, ResourceStorageCollection):
                    await self._storage(collection, desired)
                elif isinstance(collection, ResourceYAMLCollection):
                    self._yaml(collection, desired)
                else:
                    _LOGGER.error('Cannot register AERO C14 cards: unsupported Lovelace resource collection %s', type(collection).__name__)
            except Exception:
                _LOGGER.exception('Could not register AERO C14 Lovelace resources')

    async def _storage(self, collection, desired):
        await collection.async_get_info()
        items = list(collection.async_items())
        for item in items:
            if _resource_path(item) == _LEGACY_LOADER:
                await collection.async_delete_item(item['id'])
        for path, resource in desired.items():
            matches = [item for item in items if _resource_path(item) == path]
            values = {'url': resource['url'], 'res_type': 'module'}
            if not matches:
                await collection.async_create_item(values)
                continue
            first, *duplicates = matches
            if first.get('url') != resource['url'] or first.get('type') != 'module':
                await collection.async_update_item(first['id'], values)
            for duplicate in duplicates:
                await collection.async_delete_item(duplicate['id'])

    @callback
    def _yaml(self, collection, desired):
        managed = {*desired, _LEGACY_LOADER}
        items = [item for item in collection.async_items() if _resource_path(item) not in managed]
        collection.data = [*items, *(dict(resource) for resource in desired.values())]
        self._yaml_collection = collection


async def async_register_cards(hass):
    manager = hass.data.get(_MANAGER)
    if manager is None:
        manager = hass.data[_MANAGER] = CardResources(hass)
    await manager.async_register()
