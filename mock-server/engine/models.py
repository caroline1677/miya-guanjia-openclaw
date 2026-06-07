from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


@dataclass
class Tick:
    index: int
    virtual_time: str
    restaurants: Dict[str, Any]
    taxi: Dict[str, Any]
    weather_overlay: Optional[Dict[str, Any]]


@dataclass
class Watcher:
    entity_path: str          # e.g. "restaurants.海底捞福田.waiting"
    operator: str             # "<=", ">=", "=="
    threshold: Any
    callback: Callable        # fn(user_id, path, value, full_state)
    user_id: str
    fired: bool = False
