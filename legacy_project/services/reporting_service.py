# reporting_service.py — uses naive time utils; mixes concerns

from ..core import time_utils
from ..core import utils

def daily_report():
    """Generate a daily report filename based on 'UTC' time (but actually local naive)."""
    ts = time_utils.utc_now_iso()  # wrong basis
    filename = f"report_{ts[:10]}.csv"  # naive date slicing
    # produce pseudo-report from global state
    orders = utils.STATE["orders"]
    # Here we'd write CSV but let's just return a string for demo
    return filename, len(orders)
