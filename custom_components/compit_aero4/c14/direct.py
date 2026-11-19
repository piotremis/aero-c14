"""Allowlisted runtime fields in fresh Nano templates inside an owned lease."""
from .protocol import checksum_sum7


def boost_broadcast(template: bytes, enabled: bool) -> bytes:
    if (type(enabled) is not bool or len(template)!=30
            or (template[0],template[1],template[3],template[4],template[29])!=(0xE4,0x21,0x29,10,0x23)
            or any(b>=128 for b in template[1:])
            or checksum_sum7(template)!=template[2]):
        raise ValueError('Invalid Nano status template')
    raw=bytearray(template)
    raw[27]=(raw[27]|0x20) if enabled else (raw[27]&~0x20)
    raw[2]=checksum_sum7(raw)
    return bytes(raw)


def ventilation_broadcast(template: bytes, selection: str) -> bytes:
    if selection not in ('stopped', 'B1', 'B2', 'B3'):
        raise ValueError('Unsupported direct ventilation level')
    
    boost_broadcast(template, False)
    if (template[27] & 0x20 or template[11] & 8 or template[5] & 4
            or template[28] & 7 == 0):
        raise ValueError('Direct gear unavailable under an overriding mode')
    raw = bytearray(template)
    raw[28] = (raw[28] & ~7) | {'stopped': 1, 'B1': 3, 'B2': 5, 'B3': 7}[selection]
    raw[2] = checksum_sum7(raw)
    return bytes(raw)


def aero_control_poll(template: bytes) -> bytes:
    if (len(template)!=30 or (template[0],template[1],template[3],template[29])!=(0xE3,0x44,0x29,0x23)
            or template[4] not in (0x39,0x3A,0x3B) or any(b>=128 for b in template[1:])
            or checksum_sum7(template)!=template[2]):
        raise ValueError('Invalid AERO control template')
    return bytes(template)


def bypass_control(template: bytes, selection: str) -> bytes:
    aero_control_poll(template)
    if template[4] != 0x3A or template[28]&1 or selection not in ('OFF','ON'):
        raise ValueError('Unsupported direct bypass template or mode')
    raw=bytearray(template)
    raw[28]=(raw[28]&~2) | {'OFF':0,'ON':2}[selection]
    raw[2]=checksum_sum7(raw)
    return bytes(raw)


def gwc_control(template: bytes, selection: str) -> bytes:
    aero_control_poll(template)
    if template[4] != 0x39 or selection not in ('off','auto'):
        raise ValueError('Unsupported direct GWC template or mode')
    raw=bytearray(template)
    raw[12]=(raw[12]&~0x40) | (0x40 if selection=='auto' else 0)
    raw[2]=checksum_sum7(raw)
    return bytes(raw)


def fireplace_control(template: bytes, enabled: bool) -> bytes:
    aero_control_poll(template)
    if template[4] != 0x39 or type(enabled) is not bool:
        raise ValueError('Unsupported direct fireplace template or value')
    raw=bytearray(template)
    raw[28]=(raw[28]&~0x40) | (0x40 if enabled else 0)
    raw[2]=checksum_sum7(raw)
    return bytes(raw)


def power_broadcast(template: bytes, enabled: bool, resume_level=None) -> bytes:
    boost_broadcast(template, False)
    if type(enabled) is not bool:raise ValueError('Power requires boolean')
    if template[27]&0x20:raise ValueError('Nano must resolve power during boost')
    raw=bytearray(template)
    if enabled:
        if resume_level not in ('stopped','B1','B2','B3'):
            raise ValueError('A resolved Nano level is required for power ON')
        if template[5]&4 or template[28]&7==0 or template[27]&0x20:
            raise ValueError('Nano override must resolve power ON')
        raw[11]&=~8
        raw[28]=(raw[28]&~7)|{'stopped':1,'B1':3,'B2':5,'B3':7}[resume_level]
    else:
        if template[5]&4 or not template[28]&1:
            raise ValueError('Nano must resolve power OFF under an override')
        raw[11]|=8
        raw[28]=(raw[28]&~7)|1
    raw[2]=checksum_sum7(raw)
    return bytes(raw)


def holiday_broadcast(template: bytes, enabled: bool, resume_level=None) -> bytes:
    boost_broadcast(template, False)
    if type(enabled) is not bool:raise ValueError('Holiday requires boolean')
    if template[5]&4 or template[27]&0x20:
        raise ValueError('Nano override must resolve holiday transition')
    if not enabled and template[11]&8:
        raise ValueError('Power OFF takes precedence over holiday resume')
    raw=bytearray(template)
    if enabled:raw[28]&=~7
    else:
        if resume_level not in ('stopped','B1','B2','B3'):
            raise ValueError('A resolved Nano level is required after holiday')
        raw[28]=(raw[28]&~7)|{'stopped':1,'B1':3,'B2':5,'B3':7}[resume_level]
    raw[2]=checksum_sum7(raw)
    return bytes(raw)


def resolve_manual_level(fields, *, leaving_holiday=False):
    """Resolve only a fresh stored manual choice with no competing override."""
    required=('parameter_ventilation_work_mode','parameter_away_mode','boost_active')
    if not leaving_holiday:required+=('parameter_holiday_mode',)
    for name in required:
        field=fields.get(name,{})
        age=field.get('age_seconds')
        if field.get('status')!='known' or not isinstance(age,(int,float)) or not 0<=age<=30:
            return None
    if any(fields[name]['value'] is not False for name in required[1:]):return None
    return {'manual_stop':'stopped','B1':'B1','B2':'B2','B3':'B3'}.get(fields[required[0]]['value'])


def control_context(fields):
    """Keep only supported boolean settings, never synthesize live reports."""
    return {name:(info['value'],info['observed_ns']) for name in (
        'parameter_ventilation_enabled','parameter_holiday_mode','parameter_away_mode','parameter_boost')
        if (info:=fields.get(name,{})).get('status')=='known'
        and type(info.get('value')) is bool and type(info.get('observed_ns')) is int}


def context_matches_template(template, context, command_key, now):
    if context is None:return True
    own={'boost':'parameter_boost','holiday_mode':'parameter_holiday_mode',
         'ventilation_enabled':'parameter_ventilation_enabled'}.get(command_key)
    observed={'parameter_ventilation_enabled':not bool(template[11]&8),
              'parameter_holiday_mode':not bool(template[28]&1),
              'parameter_away_mode':bool(template[5]&4),
              'parameter_boost':bool(template[27]&0x20)}
    return all(name==own or (0<=now-stamp<=30_000_000_000 and observed[name] is value)
               for name,(value,stamp) in context.items())
