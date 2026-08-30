"""
Competency-gap identification for India's Official Statistical System (OSS).

A competency is a named skill domain (e.g. "Survey Methodology & Sampling
Design"). Every question in the bank is tagged with one competency id.
For a given officer (user_id), we blend three signals already produced by
the FSRS engine and the review log into a single 0-100 proficiency score
per competency:

  1. coverage   - how much of that competency's question bank they've attempted
  2. accuracy   - fraction of recent reviews rated Good/Easy (>=3)
  3. retention  - average FSRS memory stability for attempted cards,
                  i.e. how durable their recall is, not just whether they
                  answered correctly once

Competencies scoring below a threshold are surfaced as "gaps" and handed to
backend.mock_igot to attach recommended iGOT Karmayogi training.
"""

import json
import os

from backend.scheduler import load_questions, load_review_log, load_cards, DEFAULT_USER_ID

DATA_DIR = "data"
COMPETENCIES_FILE = os.path.join(DATA_DIR, "competencies.json")

# Cap on FSRS stability (days) used to normalize the retention component,
# so a handful of very mature cards don't blow the score past a realistic
# ceiling.
STABILITY_CAP_DAYS = 60
GAP_THRESHOLD = 60


def load_competency_taxonomy() -> list[dict]:
    if not os.path.exists(COMPETENCIES_FILE):
        return []
    with open(COMPETENCIES_FILE, "r") as f:
        return json.load(f)


def _questions_by_competency(user_id: str) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {}
    for q in load_questions(user_id):
        buckets.setdefault(q.get("competency", "general"), []).append(q)
    return buckets


def competency_scores(user_id: str = DEFAULT_USER_ID) -> list[dict]:
    taxonomy = load_competency_taxonomy()
    questions_by_comp = _questions_by_competency(user_id)
    cards = load_cards(user_id)
    logs = load_review_log(user_id)

    qid_to_comp = {q["id"]: q.get("competency", "general") for q in load_questions(user_id)}
    comp_review_counts: dict[str, dict] = {}
    for entry in logs:
        qid = entry.get("question_id")
        comp = qid_to_comp.get(qid)
        if comp is None:
            continue
        bucket = comp_review_counts.setdefault(comp, {"total": 0, "good": 0})
        bucket["total"] += 1
        if (entry.get("rating") or 0) >= 3:
            bucket["good"] += 1

    results = []
    for comp in taxonomy:
        comp_id = comp["id"]
        comp_questions = questions_by_comp.get(comp_id, [])

        if not comp_questions:
            results.append({
                **comp, "score": None, "questions_seen": 0,
                "questions_total": 0, "accuracy": None,
            })
            continue

        seen = 0
        stability_sum = 0.0
        for q in comp_questions:
            card_data = cards.get(q["id"])
            if card_data:
                seen += 1
                stability_sum += min(card_data.get("stability") or 0, STABILITY_CAP_DAYS)

        review_stats = comp_review_counts.get(comp_id, {"total": 0, "good": 0})
        accuracy = (review_stats["good"] / review_stats["total"]) if review_stats["total"] else None

        coverage_score = (seen / len(comp_questions)) * 100
        accuracy_score = (accuracy * 100) if accuracy is not None else 0
        retention_score = (stability_sum / seen / STABILITY_CAP_DAYS * 100) if seen else 0

        if seen == 0:
            score = 0.0
        else:
            score = round(0.25 * coverage_score + 0.45 * accuracy_score + 0.30 * retention_score, 1)

        results.append({
            **comp,
            "score": score,
            "questions_seen": seen,
            "questions_total": len(comp_questions),
            "accuracy": round(accuracy * 100, 1) if accuracy is not None else None,
        })

    return results


def identify_gaps(user_id: str = DEFAULT_USER_ID, threshold: int = GAP_THRESHOLD) -> list[dict]:
    scores = competency_scores(user_id)
    gaps = [c for c in scores if c["score"] is not None and c["questions_total"] > 0 and c["score"] < threshold]
    gaps.sort(key=lambda c: c["score"])
    return gaps


def org_wide_scores(user_ids: list[str]) -> list[dict]:
    """Average competency scores across a list of users, for the manager/admin view."""
    taxonomy = load_competency_taxonomy()
    per_user_scores = {uid: {c["id"]: c for c in competency_scores(uid)} for uid in user_ids}

    org_scores = []
    for comp in taxonomy:
        comp_id = comp["id"]
        values = [
            per_user_scores[uid][comp_id]["score"]
            for uid in user_ids
            if per_user_scores[uid][comp_id]["score"] is not None
            and per_user_scores[uid][comp_id]["questions_total"] > 0
        ]
        avg_score = round(sum(values) / len(values), 1) if values else None
        weakest_users = sorted(
            (
                (uid, per_user_scores[uid][comp_id]["score"])
                for uid in user_ids
                if per_user_scores[uid][comp_id]["score"] is not None
            ),
            key=lambda t: t[1],
        )[:3]
        org_scores.append({
            **comp,
            "avg_score": avg_score,
            "officers_assessed": len(values),
            "weakest_officers": [{"user_id": uid, "score": s} for uid, s in weakest_users],
        })

    org_scores.sort(key=lambda c: (c["avg_score"] is None, c["avg_score"]))
    return org_scores
