"""
Lightweight XP/level/leaderboard layer on top of the FSRS review flow.

XP is awarded per review (backend.scheduler.review_card calls award_xp),
weighted by the FSRS rating so genuinely knowing an answer (Easy) is worth
more than scraping past it (Again). Levels use a simple triangular curve —
each level costs 100 XP more than the last, so progress visibly slows,
which reads well on a leaderboard/level-up toast without needing tuning.
"""

import json
import os

DATA_DIR = "data"
XP_FILE = os.path.join(DATA_DIR, "xp.json")

XP_PER_RATING = {1: 2, 2: 5, 3: 10, 4: 15}  # Again, Hard, Good, Easy
LEVEL_BASE_COST = 100


def _load() -> dict:
    if not os.path.exists(XP_FILE):
        return {}
    with open(XP_FILE, "r") as f:
        return json.load(f)


def _save(data: dict) -> None:
    with open(XP_FILE, "w") as f:
        json.dump(data, f, indent=2)


def level_for_xp(xp: int) -> dict:
    """Returns level, xp progress within the current level, and xp needed
    to reach the next one — everything the UI needs for a progress bar."""
    level = 1
    remaining = xp
    needed = LEVEL_BASE_COST
    while remaining >= needed:
        remaining -= needed
        level += 1
        needed += LEVEL_BASE_COST
    return {
        "level": level,
        "xp_total": xp,
        "xp_into_level": remaining,
        "xp_for_next_level": needed,
    }


def award_xp(user_id: str, rating_val: int) -> dict:
    data = _load()
    prev_xp = data.get(user_id, 0)
    prev_level = level_for_xp(prev_xp)["level"]

    gained = XP_PER_RATING.get(rating_val, 0)
    new_xp = prev_xp + gained
    data[user_id] = new_xp
    _save(data)

    info = level_for_xp(new_xp)
    info["xp_gained"] = gained
    info["leveled_up"] = info["level"] > prev_level
    return info


def user_xp(user_id: str) -> dict:
    data = _load()
    return level_for_xp(data.get(user_id, 0))


def leaderboard(limit: int = 20) -> list[dict]:
    """Ranked by XP, opt-in users only (default opt-in — see
    backend.auth.set_leaderboard_opt_in). Imported lazily to avoid a
    module-load cycle with auth.py."""
    from backend import auth

    data = _load()
    users_by_id = {u["id"]: u for u in auth.list_users()}

    rows = []
    for user_id, xp in data.items():
        user = users_by_id.get(user_id)
        if user is None or not user.get("leaderboard_opt_in", True):
            continue
        info = level_for_xp(xp)
        rows.append({
            "user_id": user_id,
            "name": user["name"],
            "role": user["role"],
            "xp": xp,
            "level": info["level"],
        })

    rows.sort(key=lambda r: r["xp"], reverse=True)
    return rows[:limit]
