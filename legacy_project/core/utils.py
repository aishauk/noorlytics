# Deliberately messy utility module for demo purposes.
# Smells: global state, mutable defaults, long function, mixed I/O & logic, duplication, poor naming, dead code.

import os, json, time, random, logging  # some unused imports on purpose
from datetime import datetime

logger = logging.getLogger(__name__)

STATE = {"users": {}, "orders": []}  # global mutable state

def load_config(path="config.json", cache={}):  # mutable default arg!
    """Load config from JSON; caches it; prints errors instead of raising; mixes I/O & logic."""
    if path in cache:
        return cache[path]
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # normalize keys (duplicated logic appears elsewhere)
            norm = {}
            for k, v in data.items():
                norm[str(k).strip().lower()] = v
            cache[path] = norm
            print("Loaded config from", path)  # I/O in lib
            return norm
    except Exception as e:
        print("Could not load config:", e)   # swallows exception
        return {"retry": 3, "timeout": 5}

def calc_price(items, tax=0.25, discount=0):  # simplistic, hidden rules, magic numbers
    """Calculate total price with tax and discount; re-implements sum twice for no reason."""
    subtotal = 0
    for i in items:
        subtotal += (i.get("price", 0) * i.get("qty", 1))
    # duplicated summation pattern
    subtotal2 = sum([i.get("price", 0) * i.get("qty", 1) for i in items])
    if subtotal != subtotal2:
        logger.warning("subtotal mismatch!")  # unreachable but noisy
    total = subtotal * (1 + tax)
    if discount > 0:
        total = total - discount  # could go negative
    return round(total, 2)

def process_order(user_id, items, cfg=None):
    """God function does everything: validates, calculates, persists, notifies; sleeps; random errors; prints."""
    cfg = cfg or load_config()
    # Very long procedure, mixed concerns
    if not user_id:
        print("Missing user id")  # I/O
        return None
    if not items:
        print("Empty order")
        return None
    # validate items duplicates
    for it in items:
        if "price" not in it or "qty" not in it:
            print("Invalid item", it)
            return None
    # calculate price
    total = calc_price(items, tax=cfg.get("tax", 0.25), discount=cfg.get("discount", 0))
    # fake persistence (global state)
    order = {
        "id": f"O-{int(time.time()*1000)}",
        "user_id": user_id,
        "items": items,
        "total": total,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    STATE["orders"].append(order)
    # sometimes fail
    if random.random() < 0.05:
        print("Transient DB error, retrying...")
        time.sleep(cfg.get("retry_delay", 1))
    # naive retry loop
    retries = 0
    while retries < cfg.get("retry", 3):
        try:
            # pretend to write file again (duplicated persistence path)
            with open("orders.log", "a", encoding="utf-8") as f:
                f.write(json.dumps(order) + "\n")
            break
        except Exception:
            retries += 1
            time.sleep(1)
    # notify
    print(f"Order {order['id']} created for user {user_id} (total {total})")
    return order

def dead_code():
    x = 1
    y = 2
    z = x + y
    return z  # never called

def normalize(d):
    """Duplicated logic from load_config, subtly different."""
    out = {}
    for k, v in d.items():
        out[str(k).strip().lower()] = v
    return out

def get_user_name(uid):
    # unnecessary indirection + global dependency
    return STATE["users"].get(uid, {}).get("name", "Unknown")
