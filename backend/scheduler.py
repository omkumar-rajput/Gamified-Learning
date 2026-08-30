from fsrs import Scheduler, Card, Rating, ReviewLog
from datetime import datetime
import json
import os

from backend import gamification

DATA_DIR = "data"
QUESTIONS_FILE = os.path.join(DATA_DIR, "questions.json")
CARDS_FILE = os.path.join(DATA_DIR, "cards.json")
REVIEW_LOG_FILE = os.path.join(DATA_DIR, "review_log.json")

_scheduler = Scheduler()

RATING_MAP = {
    1: Rating.Again,
    2: Rating.Hard,
    3: Rating.Good,
    4: Rating.Easy,
}

# Used whenever a request doesn't specify a user (back-compat with the
# single-user version of this app), and as the migration target for any
# legacy flat cards.json / review_log.json files.
DEFAULT_USER_ID = "demo_officer_1"


def _clean_text(value: object, default: str) -> str:
    if isinstance(value, str):
        value = value.strip()
        if value:
            return value
    return default


def normalize_question(question: dict) -> dict:
    normalized = dict(question)
    normalized["subject"] = _clean_text(normalized.get("subject"), "General")
    normalized["chapter"] = _clean_text(normalized.get("chapter"), "General")
    normalized["competency"] = _clean_text(normalized.get("competency"), "general")
    normalized.setdefault("options", None)
    normalized.setdefault("correct_index", None)
    normalized.setdefault("explanation", None)
    # Back-compat: every question from before multi-user auth existed is
    # implicitly shared (the old single officer bank). Only explicitly
    # private questions (student uploads) are owner-scoped.
    normalized.setdefault("visibility", "shared")
    normalized.setdefault("owner_id", None)
    return normalized


def load_questions(user_id: str | None = None) -> list[dict]:
    """With no user_id, returns every question (internal/admin use only —
    do not expose this unfiltered to a non-admin API response). With a
    user_id, returns the shared bank plus that user's own private uploads,
    which is what every user-facing endpoint should call."""
    if not os.path.exists(QUESTIONS_FILE):
        print("File not found")
        return []
    with open(QUESTIONS_FILE, "r") as f:
        questions = [normalize_question(question) for question in json.load(f)]

    if user_id is None:
        return questions
    return [
        q for q in questions
        if q["visibility"] != "private" or q["owner_id"] == user_id
    ]


def save_questions(questions: list[dict]) -> None:
    with open(QUESTIONS_FILE, "w") as f:
        json.dump([normalize_question(question) for question in questions], f, indent=2)


def save_question(
    qid: int | None,
    front: str,
    back: str,
    subject: str | None = None,
    chapter: str | None = None,
    competency: str | None = None,
    options: list[str] | None = None,
    correct_index: int | None = None,
    explanation: str | None = None,
    owner_id: str | None = None,
    visibility: str | None = None,
) -> dict | None:
    # Unfiltered load: editing/creating must be able to see (and not
    # accidentally clobber) every question, not just the caller's visible set.
    questions = load_questions(user_id=None)
    if qid is None:
        new_id = max((q["id"] for q in questions), default=0) + 1
        new_q = {
            "id": new_id,
            "front": front,
            "back": back,
            "subject": _clean_text(subject, "General"),
            "chapter": _clean_text(chapter, "General"),
            "competency": _clean_text(competency, "general"),
            "options": options,
            "correct_index": correct_index,
            "explanation": explanation,
            "owner_id": owner_id,
            "visibility": visibility or ("private" if owner_id else "shared"),
        }
        questions.append(new_q)
        save_questions(questions)
        return new_q
    else:
        for q in questions:
            if q["id"] == qid:
                q["front"] = front
                q["back"] = back
                q["subject"] = _clean_text(subject, q.get("subject", "General"))
                q["chapter"] = _clean_text(chapter, q.get("chapter", "General"))
                q["competency"] = _clean_text(competency, q.get("competency", "general"))
                if options is not None:
                    q["options"] = options
                if correct_index is not None:
                    q["correct_index"] = correct_index
                if explanation is not None:
                    q["explanation"] = explanation
                save_questions(questions)
                return q
        return None


def build_question_catalog(user_id: str | None = None) -> dict:
    catalog: dict[str, list[str]] = {}
    for question in load_questions(user_id):
        subject = question.get("subject", "General")
        chapter = question.get("chapter", "General")
        chapters = catalog.setdefault(subject, [])
        if chapter not in chapters:
            chapters.append(chapter)

    return {
        "subjects": list(catalog.keys()),
        "chapters_by_subject": catalog,
    }


def load_users() -> list[dict]:
    """Back-compat shim: user accounts now live in the SQLite auth store
    (backend.auth), not a flat JSON file. Kept as a thin wrapper so callers
    that only need id/name/role don't have to import backend.auth directly."""
    from backend import auth
    users = auth.list_users()
    if not users:
        return [{"id": DEFAULT_USER_ID, "name": "Demo Officer", "role": "officer"}]
    return users


def resolve_user_id(requested_id: str | None) -> str:
    """Falls back to the default demo user if none/unknown is supplied."""
    users = {u["id"] for u in load_users()}
    if requested_id and requested_id in users:
        return requested_id
    return DEFAULT_USER_ID


def _load_all_cards() -> dict:
    if not os.path.exists(CARDS_FILE):
        return {}
    with open(CARDS_FILE, "r") as f:
        raw = json.load(f)
    # Migrate legacy single-user flat structure {"1": {...card...}} into the
    # nested per-user structure {"demo_officer_1": {"1": {...card...}}}.
    if raw and all(isinstance(v, dict) and "card_id" in v for v in raw.values()):
        raw = {DEFAULT_USER_ID: raw}
    return raw


def _save_all_cards(all_cards: dict) -> None:
    with open(CARDS_FILE, "w") as f:
        json.dump(all_cards, f, indent=2, default=str)


def load_cards(user_id: str) -> dict[int, dict]:
    """Card scheduling state (FSRS) is per-user; the question bank is shared."""
    all_cards = _load_all_cards()
    user_cards = all_cards.get(user_id, {})
    return {int(k): v for k, v in user_cards.items()}


def save_cards(user_id: str, cards: dict[int, dict]) -> None:
    all_cards = _load_all_cards()
    all_cards[user_id] = cards
    _save_all_cards(all_cards)


def deserialize_card(data: dict | None, now: datetime | None = None) -> Card:
    """Return a new Card for unseen questions, or restore a previously saved
    one. Pass `now` (the same timestamp the caller is filtering "due" cards
    against) when constructing a fresh card, so it's due immediately rather
    than a few microseconds in the future — Card()'s internal default is
    datetime.now() at construction time, which is always microseconds after
    any `now` an earlier caller already captured, so brand-new users (no
    cards.json entries yet - every self-serve student on their first visit)
    would otherwise see 0 due questions instead of their full deck."""
    if data is None:
        return Card(due=now) if now is not None else Card()
    return Card.from_dict(data)


def serialize_card(card: Card) -> dict:
    return card.to_dict()


def get_due_cards(user_id: str, now: datetime) -> list[dict]:
    """Merge question content with this user's card metadata for every due
    question visible to them (shared bank + their own private uploads)."""
    questions = load_questions(user_id)
    cards = load_cards(user_id)
    due = []
    for q in questions:
        qid = q["id"]
        card = deserialize_card(cards.get(qid), now)
        if card.due <= now:
            due.append({
                "id": qid,
                "front": q["front"],
                "back": q["back"],
                "subject": q.get("subject", "General"),
                "chapter": q.get("chapter", "General"),
                "competency": q.get("competency", "general"),
                "options": q.get("options"),
                "correct_index": q.get("correct_index"),
                "explanation": q.get("explanation"),
                "state": card.state,
                "due": card.due.isoformat(),
            })

    return due


def card_state_for_question(cards: dict[int, dict], qid: int) -> int:
    return deserialize_card(cards.get(qid)).state


def review_card(user_id: str, qid: int, rating_val: int, now: datetime) -> dict:
    """Apply a rating to a card, persist the updated schedule for this user,
    and award gamification XP for the review."""
    cards = load_cards(user_id)
    card = deserialize_card(cards.get(qid))
    rating = RATING_MAP[rating_val]

    card, review_log = _scheduler.review_card(card, rating, now)

    cards[qid] = serialize_card(card)
    save_cards(user_id, cards)

    save_review_log(user_id, review_log, qid)
    xp_info = gamification.award_xp(user_id, rating_val)

    return {
        "next_due": card.due.isoformat(),
        "stability": round(card.stability, 4),
        "difficulty": round(card.difficulty, 4),
        "state": card.state,
        "xp": xp_info,
    }


def load_review_log(user_id: str | None = None) -> list[dict]:
    if not os.path.exists(REVIEW_LOG_FILE):
        return []

    with open(REVIEW_LOG_FILE, "r") as f:
        logs = json.load(f)

    if user_id is None:
        return logs
    return [entry for entry in logs if entry.get("user_id") == user_id]


def save_review_log(user_id: str, review_log: ReviewLog, qid: int | None = None):
    review_logs = load_review_log()
    entry = review_log.to_dict()
    entry["user_id"] = user_id
    if qid is not None:
        entry["question_id"] = qid
    review_logs.append(entry)
    with open(REVIEW_LOG_FILE, "w") as f:
        json.dump(review_logs, f, indent=2, default=str)
