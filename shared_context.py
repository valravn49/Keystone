# shared_context.py
# Persistent “family history” and realistic media references for all siblings.

from __future__ import annotations
import os, json, random, time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# ---------------------- Storage paths ----------------------
DATA_DIR = "data"
MEMORY_PATH = os.path.join(DATA_DIR, "shared_memories.json")
MEDIA_PATH  = os.path.join(DATA_DIR, "media_catalog.json")

# ---------------------- Defaults ---------------------------
# Reasonable, real-feeling titles per category. You can expand these anytime;
# the module will merge with any existing JSON on disk.
DEFAULT_MEDIA = {
    "games": [
        # Action/Adventure
        {"title": "The Legend of Zelda: Tears of the Kingdom", "tags": ["adventure","nintendo","zelda"]},
        {"title": "Elden Ring", "tags": ["soulslike","action","fantasy"]},
        {"title": "Hades II", "tags": ["roguelike","indie"]},
        {"title": "Final Fantasy VII Rebirth", "tags": ["jrpg","final fantasy"]},
        {"title": "Baldur’s Gate 3", "tags": ["rpg","dnd"]},
        {"title": "Animal Crossing: New Horizons", "tags": ["cozy","nintendo"]},
        {"title": "League of Legends", "tags": ["moba","competitive"]},
        {"title": "Stardew Valley", "tags": ["cozy","indie","sim"]},
        {"title": "Hollow Knight", "tags": ["metroidvania","indie"]},
    ],
    "shows": [
        {"title": "Stranger Things", "tags": ["sci-fi","nostalgia"]},
        {"title": "The Last of Us", "tags": ["drama","game-adaptation"]},
        {"title": "Arcane", "tags": ["animation","league of legends"]},
        {"title": "The Bear", "tags": ["drama","slice of life"]},
        {"title": "Blue Eye Samurai", "tags": ["animation","action"]},
        {"title": "Ted Lasso", "tags": ["feel-good","comedy"]},
        {"title": "Succession", "tags": ["drama"]},
        {"title": "Demon Slayer", "tags": ["anime","action"]},
        {"title": "Frieren: Beyond Journey’s End", "tags": ["anime","calm","fantasy"]},
    ],
    "movies": [
        {"title": "Spider-Man: Across the Spider-Verse", "tags": ["animation","superhero"]},
        {"title": "Dune: Part Two", "tags": ["sci-fi","epic"]},
        {"title": "Past Lives", "tags": ["romance","drama"]},
        {"title": "Barbie", "tags": ["comedy","pop"]},
        {"title": "Oppenheimer", "tags": ["drama","historical"]},
        {"title": "Everything Everywhere All at Once", "tags": ["indie","multiverse"]},
    ],
    "books": [
        {"title": "Project Hail Mary — Andy Weir", "tags": ["sci-fi","popular"]},
        {"title": "The House in the Cerulean Sea — TJ Klune", "tags": ["cozy","fantasy"]},
        {"title": "Atomic Habits — James Clear", "tags": ["nonfiction","habits"]},
        {"title": "Ninth House — Leigh Bardugo", "tags": ["fantasy","dark"]},
        {"title": "Tomorrow, and Tomorrow, and Tomorrow — Gabrielle Zevin", "tags": ["litfic","games"]},
    ],
    "music": [
        {"title": "Lo-fi beats (Lofi Girl)", "tags": ["lofi","study"]},
        {"title": "Taylor Swift (Midnights)", "tags": ["pop"]},
        {"title": "Loathe — A New King of Pain", "tags": ["alt","metal"]},
        {"title": "City Pop Mix (Mariya Takeuchi)", "tags": ["city pop","retro"]},
    ]
}

# Very-light preference tags for flavor matching — adjust freely
SIBLING_TASTES = {
    "Aria":      {"likes": ["books","cozy","classical","lofi","slice of life","study","order"], "avoid": ["chaos","gore"]},
    "Selene":    {"likes": ["romance","slice of life","cozy","lofi","feel-good","anime"], "avoid": ["gritty"]},
    "Cassandra": {"likes": ["discipline","strategy","documentary","nonfiction","drama"], "avoid": ["aimless"]},
    "Ivy":       {"likes": ["pop","reality","competitive","spicy","banter"], "avoid": []},
    "Will":      {"likes": ["anime","jrpg","retro","sci-fi","indie","nintendo"], "avoid": ["sports sim"]},
}

# ---------------------- Disk I/O ---------------------------
def _ensure_files():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(MEMORY_PATH):
        with open(MEMORY_PATH, "w", encoding="utf-8") as f:
            json.dump({"memories": []}, f, ensure_ascii=False, indent=2)
    if not os.path.exists(MEDIA_PATH):
        with open(MEDIA_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_MEDIA, f, ensure_ascii=False, indent=2)
    else:
        # Merge in fresh defaults if any new titles were added here
        existing = _load_json(MEDIA_PATH)
        changed = False
        for cat, items in DEFAULT_MEDIA.items():
            existing.setdefault(cat, [])
            existing_titles = {i["title"] for i in existing[cat]}
            for it in items:
                if it["title"] not in existing_titles:
                    existing[cat].append(it)
                    changed = True
        if changed:
            _save_json(MEDIA_PATH, existing)

def _load_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_json(path: str, data: dict):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

_ensure_files()

# ---------------------- Memories API -----------------------
def record_shared_event(
    who: str,
    summary: str,
    tone: str = "neutral",
    tags: Optional[List[str]] = None,
    weight: float = 1.0,
) -> dict:
    """
    Add a shared family memory. Re-uses similar recent entries by boosting weight.
    """
    store = _load_json(MEMORY_PATH) or {"memories": []}
    mems: List[dict] = store.get("memories", [])

    now_ts = time.time()
    tags = tags or []
    new = {
        "id": f"m{int(now_ts)}_{random.randint(100,999)}",
        "who": who,
        "summary": summary.strip(),
        "tone": tone,
        "tags": list(sorted(set(tags))),
        "weight": float(weight),
        "timestamp": now_ts,
        "date": datetime.utcfromtimestamp(now_ts).isoformat() + "Z",
    }

    # Simple dedup: if a very similar summary exists recently, boost weight
    for m in mems[-20:]:
        if m["summary"].lower() == new["summary"].lower():
            m["weight"] = min(5.0, m.get("weight", 1.0) + weight)
            _save_json(MEMORY_PATH, {"memories": mems})
            return m

    mems.append(new)
    _save_json(MEMORY_PATH, {"memories": mems})
    return new

def get_shared_event(
    preferred_tags: Optional[List[str]] = None,
    exclude_ids: Optional[List[str]] = None,
    max_age_days: int = 120,
) -> Optional[dict]:
    """
    Fetch a memory biased by recency + weight + tag match.
    """
    store = _load_json(MEMORY_PATH) or {"memories": []}
    mems: List[dict] = store.get("memories", [])
    if not mems:
        return None

    exclude_ids = set(exclude_ids or [])
    cutoff = time.time() - (max_age_days * 86400)
    preferred_tags = [t.lower() for t in (preferred_tags or [])]

    scored: List[Tuple[float, dict]] = []
    for m in mems:
        if m["id"] in exclude_ids:
            continue
        if m["timestamp"] < cutoff:
            continue

        # Score = weight * recency factor * (1 + tag bonus)
        age_days = max(0.1, (time.time() - m["timestamp"]) / 86400.0)
        recency = 1.0 / (1.0 + age_days / 7.0)  # biased to recent weeks
        tag_bonus = 0.0
        if preferred_tags:
            mtags = [t.lower() for t in m.get("tags", [])]
            hits = len(set(mtags) & set(preferred_tags))
            tag_bonus = min(0.5, 0.15 * hits)

        score = float(m.get("weight", 1.0)) * recency * (1.0 + tag_bonus)
        scored.append((score, m))

    if not scored:
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:6]
    _, choice = random.choice(top)
    return choice

def decay_shared_memories(decay: float = 0.95, min_keep_weight: float = 0.2):
    """
    Light, periodic decay so old memories fade naturally.
    """
    store = _load_json(MEMORY_PATH) or {"memories": []}
    mems: List[dict] = store.get("memories", [])
    changed = False
    kept: List[dict] = []
    for m in mems:
        w = float(m.get("weight", 1.0)) * decay
        if w >= min_keep_weight:
            m["weight"] = round(w, 3)
            kept.append(m)
        else:
            changed = True
    if changed:
        _save_json(MEMORY_PATH, {"memories": kept})

# ---------------------- Media API --------------------------
def load_media() -> dict:
    return _load_json(MEDIA_PATH) or DEFAULT_MEDIA

def update_media_catalog(title: str, category: str, tags: Optional[List[str]] = None):
    """
    Add/merge a media item at runtime. Saved to the JSON catalog.
    """
    cat = category.lower().strip()
    store = load_media()
    store.setdefault(cat, [])
    if not any(i["title"].lower() == title.lower() for i in store[cat]):
        store[cat].append({"title": title, "tags": tags or []})
        _save_json(MEDIA_PATH, store)

def get_media_reference(
    sibling_name: str,
    category: Optional[str] = None,
    mood_tags: Optional[List[str]] = None,
    prefer_known: bool = True,
) -> Optional[dict]:
    """
    Pick a believable title. If prefer_known=True, bias to the sibling's tastes.
    """
    store = load_media()
    cats = [category] if category else list(store.keys())
    picks: List[dict] = []
    tastes = SIBLING_TASTES.get(sibling_name, {"likes": [], "avoid": []})

    for cat in cats:
        for item in store.get(cat, []):
            score = 1.0
            itags = [t.lower() for t in item.get("tags", [])]
            # Taste alignment
            if prefer_known:
                for like in tastes["likes"]:
                    if like in itags or like in item["title"].lower():
                        score += 0.6
            for avoid in tastes["avoid"]:
                if avoid in itags:
                    score -= 0.6
            # Mood tag alignment
            if mood_tags:
                for mt in [t.lower() for t in mood_tags]:
                    if mt in itags:
                        score += 0.4
            picks.append({"item": item, "score": score, "cat": cat})

    if not picks:
        return None

    # Soft top sampling
    picks.sort(key=lambda x: x["score"], reverse=True)
    top = picks[:8]
    chosen = random.choices(top, weights=[p["score"] for p in top], k=1)[0]
    out = dict(chosen["item"])
    out["category"] = chosen["cat"]
    return out

# ---------------------- Reaction helpers -------------------
def knows_media(sibling_name: str, title: str, tags: Optional[List[str]] = None) -> bool:
    """
    Heuristic: if any liked tag appears in tags/title, assume they 'know' it.
    """
    tastes = SIBLING_TASTES.get(sibling_name, {"likes": [], "avoid": []})
    title_l = title.lower()
    tags = [t.lower() for t in (tags or [])]
    for like in tastes["likes"]:
        if like in title_l or like in tags:
            return True
    return False

def craft_media_reaction(sibling_name: str, media: dict) -> str:
    """
    Short sibling-flavored reaction line to a media title.
    """
    title = media["title"]
    tags = media.get("tags", [])
    know = knows_media(sibling_name, title, tags)

    if sibling_name == "Aria":
        if know:
            return f"I actually loved {title} — it’s gentle but thoughtful; good for a quiet night."
        return f"{title} sounds nice; if it’s calm and well-paced, I’m in."

    if sibling_name == "Selene":
        if know:
            return f"{title}? That’s so sweet — perfect for a cozy evening together."
        return f"If {title} has soft moments, I’ll bring the snacks."

    if sibling_name == "Cassandra":
        if know:
            return f"{title} is solid. Structured, focused — I approve."
        return f"If {title} isn’t fluff, I’ll give it a shot."

    if sibling_name == "Ivy":
        if know:
            return f"{title}? Ugh, fine — but only if I get commentary rights. I call dibs."
        return f"{title} better be fun or I’m heckling the whole time."

    if sibling_name == "Will":
        if know:
            return f"{title}?? Okay that’s actually my jam — I’m down."
        return f"I don’t know {title} well, but if it’s chill or nerdy I’ll try."

    return f"{title} could work."

# ---------------------- Utilities for behaviors ------------
def recall_or_enrich_prompt(
    sibling_name: str,
    base_prompt: str,
    prefer_tags: Optional[List[str]] = None,
) -> Tuple[str, Optional[dict]]:
    """
    Convenience: returns (augmented_prompt, used_memory)
    If a recent memory fits, gently weave it into the prompt so the sibling
    can reference it naturally.
    """
    mem = get_shared_event(preferred_tags=prefer_tags)
    if not mem:
        return base_prompt, None
    hint = f' If it feels natural, call back to this recent family moment: "{mem["summary"]}".'
    return base_prompt + hint, mem

def remember_after_exchange(
    who: str,
    summary: str,
    tone: str = "warm",
    tags: Optional[List[str]] = None,
    weight: float = 1.0,
) -> dict:
    """
    Shortcut for behaviors to log a memory after a nice back-and-forth.
    """
    return record_shared_event(who, summary, tone=tone, tags=tags, weight=weight)
