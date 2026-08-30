"""
Mock iGOT Karmayogi connector.

This module simulates the response shape of an iGOT Karmayogi course-catalog
API so the rest of the app (recommendation engine, frontend) can be built
and demoed against a realistic integration point without requiring live
credentials to the real iGOT platform.

To swap in the real integration later: replace `load_igot_catalog()` with an
authenticated HTTP call to iGOT's course-discovery API (SSO via the National
Digital University / Karmayogi Bharat identity layer), keeping the returned
shape identical so nothing else in this file or its callers needs to change.
"""

import json
import os

DATA_DIR = "data"
IGOT_CATALOG_FILE = os.path.join(DATA_DIR, "igot_catalog.json")

IGOT_PORTAL_URL = "https://igotkarmayogi.gov.in"


def load_igot_catalog() -> dict:
    if not os.path.exists(IGOT_CATALOG_FILE):
        return {}
    with open(IGOT_CATALOG_FILE, "r") as f:
        return json.load(f)


def courses_for_competency(competency_id: str) -> list[dict]:
    return load_igot_catalog().get(competency_id, [])


def recommend_courses(gaps: list[dict]) -> list[dict]:
    """
    gaps: output of competencies.identify_gaps() - weakest first.
    Returns ranked recommendations pairing each gap with iGOT courses.
    """
    recommendations = []
    for gap in gaps:
        score = gap["score"]
        priority = "high" if score < 35 else "medium" if score < 60 else "low"
        recommendations.append({
            "competency_id": gap["id"],
            "competency_name": gap["name"],
            "score": score,
            "priority": priority,
            "courses": courses_for_competency(gap["id"]),
        })
    return recommendations
