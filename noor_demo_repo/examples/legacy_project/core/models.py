# models.py — dict soup instead of typed models; dataclass provided but unused.

from dataclasses import dataclass, field
from typing import List, Dict, Any

# Proper model (unused in legacy code)
@dataclass
class OrderItem:
    sku: str
    price: float
    qty: int = 1

@dataclass
class Order:
    id: str
    user_id: str
    items: List[OrderItem] = field(default_factory=list)
    total: float = 0.0
    created_at: str = ""

# But legacy code uses untyped dicts with inconsistent keys:
def make_item_dict(sku, price, quantity=1, **kwargs) -> Dict[str, Any]:
    # inconsistent naming: qty vs quantity
    return {"sku": sku, "price": price, "qty": quantity, **kwargs}

def total_items(items: List[Dict[str, Any]]) -> int:
    c = 0
    for it in items:
        c += it.get("qty", it.get("quantity", 1))  # inconsistencies galore
    return c
