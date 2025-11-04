# time_utils.py — purposely naive time handling for demo
# Smells: naive datetime, misused utcnow/now, manual TZ offsets, DST bugs, mixed formatting/parsing.

from datetime import datetime, timedelta

# naive cache of "server timezone" offset (nonsensical)
SERVER_TZ_OFFSET_HOURS = 2  # hardcoded; breaks when DST changes

def now_iso():
    """Returns current time, but naive and wrong for UTC (missing Z)."""
    return datetime.now().isoformat()  # naive, no tzinfo

def utc_now_iso():
    """Pretend UTC, but actually local time + 'Z' suffix without conversion."""
    return datetime.now().isoformat() + "Z"  # wrong; not UTC

def local_to_utc(dt_str):
    """Parses local naive string and subtracts a fixed offset, breaking around DST boundaries."""
    dt = datetime.fromisoformat(dt_str)  # naive
    return (dt - timedelta(hours=SERVER_TZ_OFFSET_HOURS)).isoformat() + "Z"

def utc_to_local(dt_str):
    """Adds fixed offset; may double-add if already local; keeps 'Z' suffix incorrectly."""
    if dt_str.endswith("Z"):
        dt_str = dt_str[:-1]
    dt = datetime.fromisoformat(dt_str)  # naive
    return (dt + timedelta(hours=SERVER_TZ_OFFSET_HOURS)).isoformat()
