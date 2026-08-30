from backend.scheduler import load_review_log, load_questions
import datetime
from collections import defaultdict


def _question_lookup() -> dict[int, dict]:
    return {question["id"]: question for question in load_questions()}


def _weight_for_review(reviewed_at: str, now: datetime.datetime) -> float:
    if not reviewed_at:
        return 1.0
    try:
        dt = datetime.datetime.fromisoformat(reviewed_at)
    except ValueError:
        return 1.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    age_days = max((now - dt).total_seconds() / 86400.0, 0.0)
    half_life_days = 14.0
    return 0.5 ** (age_days / half_life_days)


def heatmap(user_id: str):
    review_log = load_review_log(user_id)

    days = defaultdict(int)
    for r in review_log:
        date = datetime.datetime.fromisoformat(r["review_datetime"]).date()
        days[str(date)] += 1

    return dict(days)


def streak(user_id: str):
    freq = heatmap(user_id)
    date = datetime.datetime.now().date()
    while freq.get(str(date), 0) > 0:
        date -= datetime.timedelta(days=1)

    return (datetime.datetime.now().date() - date).days


def hard_questions(user_id: str, limit: int = 5) -> list[dict]:
    review_log = load_review_log(user_id)
    questions = _question_lookup()
    now = datetime.datetime.now(datetime.timezone.utc)
    buckets: dict[int, dict] = defaultdict(lambda: {
        "again_count": 0,
        "hard_count": 0,
        "total_reviews": 0,
        "weighted_hard": 0.0,
        "weighted_total": 0.0,
        "last_review": None,
    })

    for entry in review_log:
        question_id = entry.get("question_id")
        if question_id is None or question_id not in questions:
            continue

        bucket = buckets[question_id]
        bucket["total_reviews"] += 1
        weight = _weight_for_review(entry.get("review_datetime"), now)
        bucket["weighted_total"] += weight
        rating = entry.get("rating")
        if rating == 1:
            bucket["again_count"] += 1
            bucket["weighted_hard"] += weight
        elif rating == 2:
            bucket["hard_count"] += 1
            bucket["weighted_hard"] += weight

        reviewed_at = entry.get("review_datetime")
        if reviewed_at and (bucket["last_review"] is None or reviewed_at > bucket["last_review"]):
            bucket["last_review"] = reviewed_at

    hard_questions = []
    for question_id, bucket in buckets.items():
        hard_reviews = bucket["again_count"] + bucket["hard_count"]
        if hard_reviews == 0:
            continue

        question = questions[question_id]
        hard_questions.append({
            "id": question_id,
            "front": question.get("front", ""),
            "back": question.get("back", ""),
            "subject": question.get("subject", "General"),
            "chapter": question.get("chapter", "General"),
            "competency": question.get("competency", "general"),
            "again_count": bucket["again_count"],
            "hard_count": bucket["hard_count"],
            "hard_reviews": hard_reviews,
            "total_reviews": bucket["total_reviews"],
            "hard_ratio": round(bucket["weighted_hard"] / max(bucket["weighted_total"], 1e-6), 3),
            "last_review": bucket["last_review"],
            "hard_score": round(bucket["weighted_hard"], 3),
        })

    hard_questions.sort(
        key=lambda item: (
            item["hard_score"],
            item["hard_ratio"],
            item["hard_reviews"],
        ),
        reverse=True,
    )

    return hard_questions[:limit]


def hard_chapters_by_subject(user_id: str, limit_per_subject: int = 5, limit_subjects: int = 5) -> list[dict]:
    review_log = load_review_log(user_id)
    questions = _question_lookup()
    now = datetime.datetime.now(datetime.timezone.utc)
    chapter_buckets: dict[tuple[str, str], dict] = defaultdict(lambda: {
        "again_count": 0,
        "hard_count": 0,
        "total_reviews": 0,
        "weighted_hard": 0.0,
        "weighted_total": 0.0,
        "question_ids": set(),
        "last_review": None,
    })

    for entry in review_log:
        question_id = entry.get("question_id")
        if question_id is None or question_id not in questions:
            continue

        question = questions[question_id]
        subject = question.get("subject", "General")
        chapter = question.get("chapter", "General")
        bucket = chapter_buckets[(subject, chapter)]

        bucket["question_ids"].add(question_id)
        bucket["total_reviews"] += 1

        weight = _weight_for_review(entry.get("review_datetime"), now)
        bucket["weighted_total"] += weight

        rating = entry.get("rating")
        if rating == 1:
            bucket["again_count"] += 1
            bucket["weighted_hard"] += weight
        elif rating == 2:
            bucket["hard_count"] += 1
            bucket["weighted_hard"] += weight

        reviewed_at = entry.get("review_datetime")
        if reviewed_at and (bucket["last_review"] is None or reviewed_at > bucket["last_review"]):
            bucket["last_review"] = reviewed_at

    grouped: dict[str, list[dict]] = defaultdict(list)
    for (subject, chapter), bucket in chapter_buckets.items():
        hard_reviews = bucket["again_count"] + bucket["hard_count"]
        if hard_reviews == 0:
            continue

        grouped[subject].append({
            "subject": subject,
            "chapter": chapter,
            "question_count": len(bucket["question_ids"]),
            "again_count": bucket["again_count"],
            "hard_count": bucket["hard_count"],
            "hard_reviews": hard_reviews,
            "total_reviews": bucket["total_reviews"],
            "hard_ratio": round(bucket["weighted_hard"] / max(bucket["weighted_total"], 1e-6), 3),
            "last_review": bucket["last_review"],
            "hard_score": round(bucket["weighted_hard"], 3),
        })

    result = []
    for subject, chapters in grouped.items():
        chapters.sort(
            key=lambda item: (
                item["hard_score"],
                item["hard_ratio"],
                item["hard_reviews"],
            ),
            reverse=True,
        )
        result.append({
            "subject": subject,
            "chapters": chapters[:limit_per_subject],
        })

    result.sort(
        key=lambda item: sum(chapter["hard_reviews"] for chapter in item["chapters"]),
        reverse=True,
    )

    return result[:limit_subjects]
