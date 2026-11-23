"""Configuration validation without any Home Assistant or I/O dependency."""
import os
from .c14.transport import SerialConfig, TcpConfig, positive_seconds
from .const import (
    CONF_TRANSPORT, CONF_SERIAL_PORT, CONF_TCP_PORT, CONF_BAUD,
    CONF_STOPBITS, CONF_STALE_AFTER, CONF_CONNECT_TIMEOUT,
)


def transport_config(data):
    if type(data.get('local_polling',False)) is not bool:
        raise ValueError('Local polling must be boolean')
    if type(data.get('extended_parameters',False)) is not bool:
        raise ValueError('Extended parameters must be boolean')
    if type(data.get('disable_gateway_detection', False)) is not bool:
        raise ValueError('Disable gateway detection must be boolean')
    positive_seconds(data[CONF_STALE_AFTER], CONF_STALE_AFTER)
    if data[CONF_STALE_AFTER] > 86400 or data[CONF_STALE_AFTER] < 1:
        raise ValueError('Freshness must be between 1 and 86400 seconds')
    if data[CONF_TRANSPORT] == 'serial':
        if data.get('local_polling',False) and (data[CONF_BAUD]!=9600 or data[CONF_STOPBITS]!=1):
            raise ValueError('Local polling requires tested 9600/8N1 framing')
        return SerialConfig(data[CONF_SERIAL_PORT], baud=data[CONF_BAUD], stopbits=data[CONF_STOPBITS])
    if data[CONF_TRANSPORT] == 'tcp':
        return TcpConfig(data['host'], data[CONF_TCP_PORT], connect_timeout=data[CONF_CONNECT_TIMEOUT])
    raise ValueError('Unknown transport')


def endpoint_key(data):
    """Only duplicate detection uses endpoints; device/entity identity never does."""
    config = transport_config(data)
    if isinstance(config, SerialConfig):
        
        
        return 'serial', os.path.normcase(os.path.normpath(config.port))
    return 'tcp', config.host.strip().rstrip('.').casefold(), config.port
