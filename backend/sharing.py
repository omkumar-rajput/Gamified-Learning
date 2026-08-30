"""
Public, no-login share links for a deck of questions.

Any deck owner (a student's private upload, or an officer's shared
questions) can mint a token that resolves to a read-only, anonymous quiz —
no account needed to open it. This is deliberately separate from the FSRS
per-user scheduling: a share-link viewer answers MCQs and gets instant
right/wrong + explanation, but there's no spaced-repetition state to persist
for someone who isn't logged in.
"""

import json
import os
import time
import uuid

DATA_DIR = "data"
SHARES_FILE = os.path.join(DATA_DIR, "shares.json")


def _load() -> dict:
    if not os.path.exists(SHARES_FILE):
        return {}
    with open(SHARES_FILE, "r") as f:
        return json.load(f)


def _save(data: dict) -> None:
    with open(SHARES_FILE, "w") as f:
        json.dump(data, f, indent=2)


def create_share(owner_id: str, question_ids: list[int], title: str = "") -> str:
    data = _load()
    token = uuid.uuid4().hex[:10]
    data[token] = {
        "owner_id": owner_id,
        "question_ids": question_ids,
        "title": title or "Shared quiz",
        "created_at": time.time(),
    }
    _save(data)
    return token


def resolve_share(token: str) -> dict | None:
    return _load().get(token)
