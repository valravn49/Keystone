# topic_knowledge.py
# Shared topic knowledge for all siblings, based on their profiles

from typing import Optional

TOPIC_KNOWLEDGE = {
    "Aria": {
        "likes": ["literature", "poetry", "skincare", "classical music", "quiet games"],
        "dislikes": ["loud games", "crude jokes", "messiness"],
        "neutral": ["anime", "technology", "fashion"],
    },
    "Selene": {
        "likes": ["skincare", "gardening", "romance stories", "cooking", "soft music"],
        "dislikes": ["violence", "competitive games", "neglect"],
        "neutral": ["anime", "tech", "books"],
    },
    "Cassandra": {
        "likes": ["discipline", "structure", "strategy games", "fitness", "order"],
        "dislikes": ["laziness", "sloppiness", "excuses"],
        "neutral": ["anime", "romance stories", "tech"],
    },
    "Ivy": {
        "likes": ["anime", "games", "memes", "teasing", "cosplay"],
        "dislikes": ["being ignored", "rules", "boring chores"],
        "neutral": ["literature", "skincare"],
    },
    "Will": {
        "likes": ["tech", "games", "anime", "music", "cosplay", "PC building"],
        "dislikes": ["drama", "arguments", "pressure"],
        "neutral": ["skincare", "gardening", "fashion"],
    },
}


def match_topic(sibling: str, message: str) -> Optional[str]:
    """Check if a message mentions something in likes/dislikes/neutral for the given sibling."""
    if sibling not in TOPIC_KNOWLEDGE:
        return None

    profile = TOPIC_KNOWLEDGE[sibling]
    lower_msg = message.lower()

    for kw in profile["likes"]:
        if kw.lower() in lower_msg:
            return "like"
    for kw in profile["dislikes"]:
        if kw.lower() in lower_msg:
            return "dislike"
    for kw in profile["neutral"]:
        if kw.lower() in lower_msg:
            return "neutral"
    return None
