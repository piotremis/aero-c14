"""Transport-independent AERO 4 state with per-field freshness, no command path."""
from copy import deepcopy
from .decode import STATE_FIELDS, decode
from .protocol import Frame


PARAMETER_CACHE_NS = 1_200_000_000_000


class Aero4State:
    def __init__(self, *, stale_after_ns: int):
        if type(stale_after_ns) is not int or stale_after_ns <= 0:
            raise ValueError("stale_after_ns must be a positive integer")
        self.stale_after_ns = stale_after_ns
        self.reset()

    def reset(self):
        """Connection reset: await new data rather than revive a cache."""
        self._fields = {}
        self.last_frame_observed_ns = None
        self.last_aero_observed_ns = None

    def update(self, frame: Frame):
        data = decode(frame)
        if not data["valid"]:
            return False
        observed = frame.last_observed_ns
        if type(observed) is not int or observed < 0:
            raise ValueError("State updates require nonnegative observed timestamps")
        if self.last_frame_observed_ns is not None and observed < self.last_frame_observed_ns:
            raise ValueError("Timestamp moved backwards; reset state for a new session")
        self.last_frame_observed_ns = observed
        if data["role"] in ("aero_reported_state", "aero_secondary_report"):
            self.last_aero_observed_ns = observed
        for name, value in data["values"].items():
            self._fields[name] = {"value": value, "observed_ns": observed,
                "source_key": frame.key, "source_offset": frame.offset,
                **deepcopy(data["quality"][name])}
        return True

    def snapshot(self, now_ns: int):
        if type(now_ns) is not int or now_ns < 0:
            raise ValueError("now_ns must be a nonnegative integer")
        if self.last_frame_observed_ns is not None and now_ns < self.last_frame_observed_ns:
            raise ValueError("Snapshot time precedes received data")

        def online(stamp, threshold=None):
            return stamp is not None and now_ns - stamp <= (threshold or self.stale_after_ns)

        def field(info, *, parameter=False):
            if info is None:
                return {"value": None, "status": "unknown", "observed_ns": None}
            result = deepcopy(info)
            result["value_status"] = info["status"]
            result["age_seconds"] = (now_ns - info["observed_ns"]) / 1e9
            
            
            if not online(info["observed_ns"], max(self.stale_after_ns, PARAMETER_CACHE_NS) if parameter else None):
                result["value"] = None
                result["status"] = "unavailable"
            elif info["value"] is None:
                result["status"] = "unknown"
            return result

        fields = {name: field(self._fields.get(name), parameter=(name.startswith('parameter_') or
                    name in ('bypass_readback','boost_readback','ventilation_mode_readback'))) for name in STATE_FIELDS}
        
        
        if fields['room_humidity_precise']['status'] == 'known':
            fields['room_humidity'] = deepcopy(fields['room_humidity_precise'])
        return {"device": "AERO 4", "at_elapsed_ns": now_ns,
                "stale_after_seconds": self.stale_after_ns / 1e9,
                "parameter_stale_after_seconds": max(self.stale_after_ns, PARAMETER_CACHE_NS) / 1e9,
                "bus_online": online(self.last_frame_observed_ns),
                "aero_online": online(self.last_aero_observed_ns),
                "last_frame_observed_ns": self.last_frame_observed_ns,
                "last_aero_observed_ns": self.last_aero_observed_ns,
                "fields": fields}
