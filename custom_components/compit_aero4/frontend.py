"""Serve bundled cards and load them without manual dashboard resources."""
import hashlib
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig

_ASSETS = ('aero4-loader.js', 'aero4-card.js', 'aero4-schedule-card.js')
_REGISTERED = 'compit_aero4_frontend_registered'


async def async_register_cards(hass):
    """Register once per HA process; headless installations need no cards."""
    if _REGISTERED in hass.data or 'frontend' not in hass.config.components:
        return

    def files():
        folder = Path(__file__).parent / 'frontend'
        paths = [folder / name for name in _ASSETS]
        digest = hashlib.sha256(b''.join(path.read_bytes() for path in paths)).hexdigest()[:12]
        return paths, digest

    paths, digest = await hass.async_add_executor_job(files)
    await hass.http.async_register_static_paths([
        StaticPathConfig(f'/compit_aero4/{path.name}', str(path), False)
        for path in paths
    ])
    frontend.add_extra_js_url(hass, f'/compit_aero4/aero4-loader.js?v={digest}')
    hass.data[_REGISTERED] = True
