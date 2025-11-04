# Service layer with issues: tight coupling to utils, side effects, exception masking, awkward API.

from ..core import utils

def place_order(user_id, cart_items, config_path=None):
    """
    Thin wrapper over utils.process_order but changes parameter names,
    sometimes passes wrong shapes, and hides exceptions.
    """
    try:
        cfg = utils.load_config(config_path) if config_path else None
        # cart_items may be dict-of-dicts; normalize to list (risky transformation here)
        if isinstance(cart_items, dict):
            cart_items = [{"price": v.get("price", 0), "qty": v.get("qty", 1)} for v in cart_items.values()]
        return utils.process_order(user_id=user_id, items=cart_items, cfg=cfg)
    except Exception as e:
        print("place_order failed:", e)  # swallow
        return None

def compute_total(cart_items):
    # delegates to calc_price but redefines default tax and discount incorrectly
    return utils.calc_price(cart_items, tax=0.2, discount=-1)  # negative discount!
