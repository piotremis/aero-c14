"""Eight-day native Nano schedule; no conversion to HA's unrelated scheduler."""
from .parameters import PARAMETERS, SCHEDULE_DAYS


def period_keys(day, period):
    if not isinstance(day, str) or day not in SCHEDULE_DAYS or type(period) is not int or not 1 <= period <= 3:
        raise ValueError('Invalid Nano day or period')
    return tuple(f'schedule_{day}_{period}_{boundary}' for boundary in ('start', 'end'))


def plan_period(day, period, start, end, current_start, current_end):
    """Validate all changes first, then order two independently confirmed writes.

    This is not an atomic transaction. Prefer intermediates with start < end;
    a failed second write leaves a partial change for the caller to review.
    Never invent a rollback that might overwrite a concurrent Nano edit.
    """
    keys = period_keys(day, period)
    start_parameter, end_parameter = (PARAMETERS[key] for key in keys)
    first, last = start_parameter.encode(start), end_parameter.encode(end)
    old_first, old_last = start_parameter.encode(current_start), end_parameter.encode(current_end)
    if not (first == last == 0 or first < last):
        raise ValueError('Only same-day intervals or 00:00/00:00 disabled periods are supported')
    desired = {keys[0]: start, keys[1]: end}
    current = {keys[0]: current_start, keys[1]: current_end}
    order = keys if first < old_last or last == 0 else tuple(reversed(keys))
    return tuple((key, desired[key]) for key in order if desired[key] != current[key])


def schedule_snapshot(fields):
    result = {}
    for day in SCHEDULE_DAYS:
        periods = []
        for period in range(1, 4):
            keys = period_keys(day, period)
            states = [fields[PARAMETERS[key].field] for key in keys]
            known = all(state['status'] == 'known' for state in states)
            periods.append({'period': period, 'start': states[0]['value'] if known else None,
                            'end': states[1]['value'] if known else None,
                            'status': 'known' if known else 'unavailable'})
        result[day] = periods
    return result
