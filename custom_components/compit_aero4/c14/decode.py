"""Decode C14 telemetry and parameter readbacks."""
from .protocol import AIR_QUALITY_FRAME_KEY, Frame, checksum_sum7
from .parameters import BY_ADDRESS, PARAMETERS

AIR_QUALITY_FIELDS = ('air_pm25_percent', 'air_pm10_percent', 'air_co2')


def _air_quality_pair(high, low):
    
    pair = (high & 0x7F, low & 0x7F)
    if pair in ((0x7E, 0x7E), (0x7F, 0x7F)):
        return None
    value = pair[0] * 128 + pair[1] - 2000
    return value if value >= 0 else None


def temperature(high: int, low: int) -> float | None:
    
    if high == 0x7E:
        return None
    value = (128 * high + low % 128 - 2000) / 10.0
    return value if -50 <= value <= 100 else None


def _percent(value: int) -> int | None:
    return value if 0 <= value <= 100 else None


def _valid(frame: Frame) -> bool:
    return (frame.checksum_valid is True and frame.checksum_rule == "sum7"
            and frame.raw[29] == 0x23 and checksum_sum7(frame.raw) == frame.raw[2])


def decode(frame: Frame, *, raw_only: bool = False) -> dict:
    f = frame.raw
    valid = _valid(frame)
    result = {"device": "AERO 4", "valid": valid, "frame_key": frame.key,
              "group_key": frame.group_key, "role": "unmapped", "values": {},
              "quality": {}, "known_masks": {},
              "unknown_offsets": list(range(4, 29)), "unknown_bits": {}}
    if raw_only or not valid:
        return result
    masks = {i: 0 for i in range(4, 29)}

    def put(name, value, offsets, *, mask=None,
            unknown_reason="unmapped_or_invalid_value"):
        info = {"offsets": list(offsets),
                "status": "known" if value is not None else unknown_reason}
        if mask is not None:
            info["mask"] = f"{mask:02X}"
        result["values"][name] = value
        result["quality"][name] = info
        for offset in offsets:
            masks[offset] |= mask if mask is not None else 0xFF

    def temp(name, offset):
        put(name, temperature(f[offset], f[offset + 1]), (offset, offset + 1))
        masks[offset + 1] = 0x7F

    if frame.key == AIR_QUALITY_FRAME_KEY:
        result['role'] = 'air_quality_report'
        
        
        for name, offset in zip(AIR_QUALITY_FIELDS, (14, 16, 18)):
            put(name, _air_quality_pair(f[offset], f[offset + 1]),
                (offset, offset + 1),
                unknown_reason='invalid_air_quality_measurement')
            masks[offset] = masks[offset + 1] = 0x7F
    elif frame.key == "E4/21/29":
        result["role"] = "nano_request_observed"
        temp("room_temperature", 12)
        temp("room_temperature_setpoint", 14)
        
        
        put("room_humidity", _percent(f[23]), (23,))
        speed = f[28] & 7
        
        
        put("ventilation_requested", {1: "stopped", 3: "B1", 5: "B2", 7: "B3"}.get(speed),
            (28,),
            mask=7, unknown_reason="unsupported_value")
        put("boost_requested", bool(f[27] & 0x20), (27,), mask=0x20)
    elif frame.key == "E4/21/63":
        result["role"] = "aero_reported_state"
        temp("outdoor_temperature", 10)
        temp("supply_temperature", 12)
        
        
        put("ventilation_reported_level", {0: "stopped", 1: "B1", 2: "B2", 3: "B3", 4: "boost"}.get(f[8] & 7),
            (8,), mask=7, unknown_reason="unsupported_value")
        put("fan_a_percent", _percent(f[25]), (25,))
        put("fan_b_percent", _percent(f[26]), (26,))
        put("boost_active", bool(f[27] & 8), (27,), mask=8)
        put("bypass_reported_open", bool(f[28] & 0x20), (28,), mask=0x20)
        put("gwc_reported_active", bool(f[28] & 0x04), (28,), mask=0x04)
        
        put("ao3_percent", _percent(f[22]), (22,))
    elif frame.key == "E5/21/29":
        result["role"] = "nano_settings_observed"


        known_layout = f[25] & 0xA8 == 0x28
        bypass = {0: "OFF", 1: "AUTO", 2: "ON"}.get(f[25] & 3) if known_layout else None
        put("bypass_requested", bypass, (25,), mask=0x03,
            unknown_reason="unsupported_value")
        
        
        reminder = bool(f[25] & 0x10) if f[25] & 0xA8 == 0x28 else None
        put("filter_maintenance_due", reminder, (25,), mask=0x10)
        put("ventilation_mode_requested", {0: "stopped", 1: "B1", 2: "B2", 3: "B3", 5: "schedule"}.get(f[28]),
            (28,), unknown_reason="unsupported_value")
    elif frame.key == "E5/21/63":
        result["role"] = "aero_secondary_report"
        temp("exhaust_temperature", 16)
        temp("extract_temperature", 18)
    elif frame.key == "E3/44/29":
        result["role"] = "nano_parameter_block"
        result["subtype_hex"] = f"{f[4]:02X}"
        masks[4] = 0xFF
        if f[4] == 0x39:
            
            
            put('fan_runon_duration', f[17] if f[17] <= 100 else None, (17,))
    elif (f[0], f[1], f[3]) in {
        (0xA9, 0x52, 0x70), (0xA9, 0x54, 0x70), (0xA9, 0x57, 0x70),
        (0xF0, 0x72, 0x29), (0xF0, 0x74, 0x29), (0xF0, 0x77, 0x29),
    }:
        kind = {0x52: "query", 0x54: "query", 0x57: "write_request",
                0x72: "readback", 0x74: "readback", 0x77: "write_echo"}[f[1]]
        result["role"] = f"parameter_{kind}_observed"
        result["parameter_records"] = []
        for offset in range(5, 29, 4):
            address = f[offset:offset + 2].hex().upper()
            if address == "0000":
                continue
            h, low = f[offset + 2:offset + 4]
            encoded = None if kind == "query" else h * 128 + low % 128 - 2000
            result["parameter_records"].append({"address_hex": address,
                "raw_value_hex": f[offset + 2:offset + 4].hex().upper(),
                "encoded_integer": encoded, "kind": kind})
            if kind != "readback":
                continue
            if f[1] == 0x74:
                
                if address == '0010':
                    put('room_humidity_precise', encoded / 10 if 0 <= encoded <= 1000 else None,
                        range(offset, offset + 4), unknown_reason='invalid_humidity_telemetry')
                continue
            parameter = BY_ADDRESS.get(address)
            if parameter is not None:
                put(parameter.field, parameter.decode(encoded), range(offset, offset + 4),
                    unknown_reason="unmapped_or_invalid_parameter")
            
            mapping = {
                "004F": ("bypass_readback", {0: "OFF", 1: "AUTO", 2: "ON"}),
                "0050": ("ventilation_mode_readback", {0: "stopped", 1: "B1", 2: "B2", 3: "B3", 4: "holiday_schedule", 5: "schedule"}),
                "0051": ("boost_readback", {0: False, 1: True}),
            }.get(address)
            if mapping:
                name, enum = mapping
                put(name, enum.get(encoded), range(offset, offset + 4),
                    unknown_reason="unsupported_value")

    result["known_masks"] = {str(i): f"{mask:02X}" for i, mask in masks.items() if mask}
    result["unknown_offsets"] = [i for i, mask in masks.items() if not mask]
    result["unknown_bits"] = {str(i): f"{(~mask & 0xFF):02X}"
                              for i, mask in masks.items() if 0 < mask < 0xFF}
    return result


STATE_FIELDS = AIR_QUALITY_FIELDS + (
    "fan_runon_duration",
    "ao3_percent",
    "room_humidity",
    "room_humidity_precise",
    "room_temperature", "room_temperature_setpoint", "outdoor_temperature", "supply_temperature",
    "exhaust_temperature", "extract_temperature",
    "ventilation_reported_level", "ventilation_requested", "ventilation_mode_requested", "boost_requested", "boost_active",
    "bypass_requested", "bypass_reported_open", "fan_a_percent", "fan_b_percent",
    "bypass_readback", "ventilation_mode_readback", "boost_readback",
    "filter_maintenance_due",
    "gwc_reported_active",
) + tuple(parameter.field for parameter in PARAMETERS.values())
