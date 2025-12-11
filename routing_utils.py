# routing_utils.py
from dataclasses import dataclass
from typing import Optional, Dict

import discord  # type: ignore

@dataclass
class SenderInfo:
    discord_id: int
    display_name: str
    is_bot: bool
    is_sister: bool
    sister_name: Optional[str]
    kind: str  # "human" | "sister" | "system" | "other_bot"


def classify_sender(
    message: discord.Message,
    sister_id_map: Optional[Dict[int, str]] = None,
) -> SenderInfo:
    """
    Classify the message author into human / sister / other_bot.
    sister_id_map: mapping from Discord user ID -> sister name (e.g. {123: "Aria"}).
    """
    author = message.author
    sister_name = None
    is_sister = False
    kind: str

    if sister_id_map and author.id in sister_id_map:
        sister_name = sister_id_map[author.id]
        is_sister = True

    if author.bot:
        if is_sister:
            kind = "sister"
        else:
            kind = "other_bot"
    else:
        kind = "human"

    return SenderInfo(
        discord_id=author.id,
        display_name=getattr(author, "display_name", author.name),
        is_bot=author.bot,
        is_sister=is_sister,
        sister_name=sister_name,
        kind=kind,
    )


def resolve_author_label(sender: SenderInfo) -> str:
    """
    Turn SenderInfo into the logical `author` label you pass into the
    sibling handlers.

    - Sister bots: their configured sister_name (e.g. "Aria")
    - Human: "you"
    - Other bots: the display_name
    """
    if sender.kind == "sister" and sender.sister_name:
        return sender.sister_name
    if sender.kind == "human":
        return "you"
    # fallback: other bots / unknown
    return sender.display_name or "unknown"
