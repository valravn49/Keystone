# messaging_utils.py
import asyncio
import random
from typing import List, Optional
from logger import log_event


def _split_into_chunks(text: str, max_len: int = 220) -> List[str]:
    """
    Split a long reply into smaller, chat-friendly chunks.
    Priority: sentence-ish boundaries, then hard cut.
    """
    text = text.strip()
    if not text:
        return []

    if len(text) <= max_len:
        return [text]

    # First pass: split on ". " and rebuild into chunks
    raw_parts = text.replace("\n", " ").split(". ")
    sentences: List[str] = []
    buf: List[str] = []

    for part in raw_parts:
        part = part.strip()
        if not part:
            continue
        # try to keep sentences small enough to recombine later
        if sum(len(x) for x in buf) + len(buf) + len(part) <= max_len:
            buf.append(part)
        else:
            sentences.append(". ".join(buf).strip())
            buf = [part]
    if buf:
        sentences.append(". ".join(buf).strip())

    chunks: List[str] = []
    current = ""

    for sent in sentences:
        candidate = (current + " " + sent).strip() if current else sent
        if len(candidate) <= max_len:
            current = candidate
        else:
        # flush current and start a new chunk
            if current:
                chunks.append(current)
            current = sent

    if current:
        chunks.append(current)

    # Final safety: hard-cut any monster segments
    final_chunks: List[str] = []
    for c in chunks:
        if len(c) <= max_len:
            final_chunks.append(c)
        else:
            # brute-force chop
            start = 0
            while start < len(c):
                final_chunks.append(c[start:start + max_len])
                start += max_len

    return [c.strip() for c in final_chunks if c.strip()]


async def send_human_like_message(
    channel,
    text: str,
    *,
    speaker_name: Optional[str] = None,
    base_typing_delay: float = 0.5,
    jitter: float = 0.8,
    multi_message_chance: float = 0.45,
) -> None:
    """
    Send a message in a more human-like way:
      - optional multi-message split
      - typing indicator
      - length-based delay
    """
    text = text.strip()
    if not text:
        return

    chunks = _split_into_chunks(text)

    # Sometimes force it into a single message so not everything is split
    if len(chunks) > 1 and random.random() > multi_message_chance:
        chunks = [" ".join(chunks)]

    for idx, chunk in enumerate(chunks):
        # Delay based on length + jitter
        char_factor = min(5.0, 0.02 * len(chunk))
        delay = base_typing_delay + char_factor + random.uniform(0, jitter)

        async with channel.typing():
            await asyncio.sleep(delay)

        await channel.send(chunk)
        who = speaker_name or "Unknown"
        log_event(f"[HUMAN_SEND] {who}: {chunk}")

        if idx < len(chunks) - 1:
            # Small pause between multi-part messages
            await asyncio.sleep(random.uniform(0.6, 2.2))
