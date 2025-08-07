# ~/auroch/gui/data_structures.py
from dataclasses import dataclass

@dataclass
class Action:
    """A simple data class to hold a single user-defined action."""
    action_type: str
    target_bbox: list[int]
    value: str = "" # Optional value, e.g., for typing