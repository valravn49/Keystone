# routing_utils.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class SenderInfo:
    discord_id: int
    display_name: str
    is_bot: bool
    is_sister: bool
    sister_name: Optional[str]  # "Aria", "Selene", etc. or None
    kind: str                   # "human", "sister", "system", "other_bot"
