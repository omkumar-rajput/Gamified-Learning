import json
import os

from flask import Flask, jsonify, request, render_template, session
from flask_cors import CORS
from datetime import datetime, timedelta, timezone
from backend.scheduler import *
from backend import auth, settings, sharing, gamification
import backend.generate as generate
import backend.stats as stats
import backend.competencies as competencies
import backend.mock_igot as mock_igot
import requests

app = Flask(__name__, template_folder="frontend", static_folder="frontend", static_url_path="")
app.secret_key = os.environ.get("SECRET_KEY", "sih26101-dev-secret-change-in-prod")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
CORS(app, supports_credentials=True)

auth.init_db()
settings.init_db()


def get_user_id() -> str | None:
    """The logged-in user's id, from the session cookie. Every data-bearing
    route below is wrapped in @auth.login_required, so this is only None if
    that decorator was forgotten on a route — treat it as a bug, not a
    fallback to handle."""
    user = auth.current_user()
    return user["id"] if user else None


@app.route("/")
def index():
    return render_template("index.html")


# ── Auth ──────────────────────────────────────────────────────────────────

@app.route("/api/auth/signup", methods=["POST"])
def signup():
    """Public self-signup — always creates a 'student' account. Officer/admin
    accounts can only be created by an admin (see /api/admin/people)."""
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    try:
        user = auth.create_user(name, email, password, role="student", created_by="self")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    auth.login_user(user)
    return jsonify({"user": user})


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = auth.verify_login(email, password)
    if user is None:
        return jsonify({"error": "Invalid email or password"}), 401

    auth.login_user(user)
    return jsonify({"user": user})


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    auth.logout_user()
    return jsonify({"ok": True})


@app.route("/api/auth/me", methods=["GET"])
def me():
    user = auth.current_user()
    return jsonify({"user": user})


# ── Admin: people + AI settings ─────────────────────────────────────────────

@app.route("/api/admin/people", methods=["GET"])
@auth.admin_required
def admin_list_people():
    return jsonify({"people": auth.list_users(active_only=False)})


@app.route("/api/admin/people", methods=["POST"])
@auth.admin_required
def admin_create_person():
    """Admin-only officer/admin provisioning — this is the 'full control,
    only I can add officers' requirement. Students self-signup instead."""
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = data.get("role") or "officer"
    title = (data.get("title") or "").strip() or None

    if role not in ("officer", "admin"):
        return jsonify({"error": "role must be 'officer' or 'admin'"}), 400

    try:
        user = auth.create_user(name, email, password, role=role, title=title,
                                 created_by=get_user_id())
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"user": user}), 201


@app.route("/api/admin/people/<user_id>", methods=["PATCH"])
@auth.admin_required
def admin_update_person(user_id):
    data = request.get_json(silent=True) or {}
    if "active" not in data:
        return jsonify({"error": "Missing field: active"}), 400
    if user_id == get_user_id() and not data["active"]:
        return jsonify({"error": "You cannot deactivate your own account"}), 400

    updated = auth.set_user_active(user_id, bool(data["active"]))
    if updated is None:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"user": updated})


@app.route("/api/admin/settings", methods=["GET"])
@auth.admin_required
def admin_get_settings():
    return jsonify({
        "ai_api_key_masked": settings.mask_key(settings.get_setting("ai_api_key")),
        "ai_provider": settings.get_setting("ai_provider", "openrouter"),
        "ai_model": settings.get_setting("ai_model", "openrouter/free"),
        "has_env_fallback": bool(
            os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
        ),
    })


@app.route("/api/admin/settings", methods=["POST"])
@auth.admin_required
def admin_set_settings():
    data = request.get_json(silent=True) or {}
    if data.get("ai_api_key"):
        settings.set_setting("ai_api_key", data["ai_api_key"].strip())
    if data.get("ai_provider"):
        settings.set_setting("ai_provider", data["ai_provider"].strip())
    if data.get("ai_model"):
        settings.set_setting("ai_model", data["ai_model"].strip())
    return jsonify({"ok": True})


# ── Questions / catalog ──────────────────────────────────────────────────

@app.route("/api/get_questions", methods=["GET"])
@auth.login_required
def get_questions():
    """
    GET /get_questions

    Response:
    {
        "due_count": 2,
        "questions": [
            {
                "id": 1,
                "front": "What is 2+2?",
                "back": "4",
                "subject": "...", "chapter": "...", "competency": "...",
                "options": ["2", "3", "4", "5"] | null,
                "correct_index": 2 | null,
                "explanation": "..." | null,
                "state": 0,
                "due": "2025-01-01T00:00:00+00:00"
            }
        ]
    }

    state: 0=New, 1=Learning, 2=Review, 3=Relearning
    """
    user_id = get_user_id()
    now = datetime.now(timezone.utc)
    due = get_due_cards(user_id, now)
    return jsonify({"due_count": len(due), "questions": due})


@app.route("/api/all_questions", methods=["GET"])
@auth.login_required
def get_all_questions():
    questions = load_questions(get_user_id())
    return jsonify({"questions": questions})


@app.route("/api/catalog", methods=["GET"])
@auth.login_required
def get_catalog():
    return jsonify(build_question_catalog(get_user_id()))


@app.route("/api/competency_taxonomy", methods=["GET"])
@auth.login_required
def get_competency_taxonomy():
    """Raw competency list (id/name/description), with no per-user scoring.
    Used to populate dropdowns on the Manage/Upload pages."""
    return jsonify({"competencies": competencies.load_competency_taxonomy()})


@app.route("/api/competencies", methods=["GET"])
@auth.login_required
def get_competencies():
    """Per-user competency proficiency, used for the dashboard radar chart."""
    user_id = get_user_id()
    return jsonify({
        "user_id": user_id,
        "competencies": competencies.competency_scores(user_id),
    })


@app.route("/api/recommendations", methods=["GET"])
@auth.login_required
def get_recommendations():
    """Competency gaps ranked weakest-first, each paired with recommended
    iGOT Karmayogi training (mocked catalog; see backend/mock_igot.py)."""
    user_id = get_user_id()
    gaps = competencies.identify_gaps(user_id)
    return jsonify({
        "user_id": user_id,
        "gaps": gaps,
        "recommendations": mock_igot.recommend_courses(gaps),
        "igot_portal_url": mock_igot.IGOT_PORTAL_URL,
    })


@app.route("/api/admin/overview", methods=["GET"])
@auth.admin_required
def get_admin_overview():
    """Aggregate competency view across all OSS officers, for a training
    manager — students self-serve outside this org-wide view by design."""
    users = [u for u in auth.list_users() if u.get("role") == "officer"]
    user_ids = [u["id"] for u in users]
    org_scores = competencies.org_wide_scores(user_ids) if user_ids else []

    per_officer = []
    for u in users:
        now = datetime.now(timezone.utc)
        gaps = competencies.identify_gaps(u["id"])
        per_officer.append({
            "user_id": u["id"],
            "name": u.get("name", u["id"]),
            "due_count": len(get_due_cards(u["id"], now)),
            "streak": stats.streak(u["id"]),
            "gap_count": len(gaps),
            "weakest_competency": gaps[0]["name"] if gaps else None,
        })

    return jsonify({
        "officers": per_officer,
        "org_competency_scores": org_scores,
    })


@app.route("/api/save_question", methods=["POST"])
@auth.login_required
def api_save_question():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    user = auth.current_user()
    qid = data.get("id")
    front = data.get("front")
    back = data.get("back")
    subject = data.get("subject")
    chapter = data.get("chapter")
    competency = data.get("competency")
    options = data.get("options")
    correct_index = data.get("correct_index")
    explanation = data.get("explanation")

    if not front or not back:
        return jsonify({"error": "Missing front or back"}), 400

    owner_id, visibility = None, "shared"
    if qid is None:
        # Officers/admins edit the shared bank; students create private cards.
        if user["role"] == "student":
            owner_id, visibility = user["id"], "private"
    else:
        existing = next((q for q in load_questions(None) if q["id"] == qid), None)
        if existing is None:
            return jsonify({"error": f"Question id '{qid}' not found"}), 404
        can_edit = (
            existing.get("owner_id") == user["id"]
            or (existing.get("visibility", "shared") == "shared" and user["role"] in ("officer", "admin"))
        )
        if not can_edit:
            return jsonify({"error": "You don't have permission to edit this question"}), 403

    updated = save_question(qid, front, back, subject, chapter, competency,
                             options, correct_index, explanation, owner_id, visibility)
    if not updated:
        return jsonify({"error": f"Question id '{qid}' not found"}), 404

    return jsonify(updated)


@app.route("/api/review", methods=["POST"])
@auth.login_required
def review():
    """
    POST /review

    Request:
    {
        "id": 1,
        "rating": 3
    }

    rating: 1=Again, 2=Hard, 3=Good, 4=Easy

    Response:
    {
        "id": 1,
        "rating": 3,
        "next_due": "2025-01-04T00:00:00+00:00",
        "stability": 4.0729,
        "difficulty": 5.0,
        "state": 2,
        "xp": { "level": 2, "xp_total": 120, "xp_gained": 10, "leveled_up": false, ... }
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    user_id = get_user_id()
    qid = data.get("id")
    rating_val = data.get("rating")

    if qid is None:
        return jsonify({"error": "Missing field: id"}), 400
    if not isinstance(qid, int):
        return jsonify({"error": "id must be an integer"}), 400
    if rating_val not in RATING_MAP:
        return jsonify({"error": "rating must be 1 (Again), 2 (Hard), 3 (Good), or 4 (Easy)"}), 400

    questions = load_questions(user_id)
    if not any(q["id"] == qid for q in questions):
        return jsonify({"error": f"Question id '{qid}' not found"}), 404

    now = datetime.now(timezone.utc)
    result = review_card(user_id, qid, rating_val, now)

    return jsonify({"id": qid, "rating": rating_val, **result})


@app.route("/api/get_review_log", methods=["GET"])
@auth.login_required
def get_review_log():
    user_id = get_user_id()
    return jsonify(load_review_log(user_id))


@app.route("/api/stats", methods=["GET"])
@auth.login_required
def get_stats():
    user_id = get_user_id()
    questions = load_questions(user_id)
    now = datetime.now(timezone.utc)
    cards = load_cards(user_id)

    due_count = len(get_due_cards(user_id, now))
    learning_count = sum(
        1 for q in questions if card_state_for_question(cards, q["id"]) in [0, 1, 3]
    )
    total_count = len(questions)
    hard_questions = stats.hard_questions(user_id)
    hard_chapters_by_subject = stats.hard_chapters_by_subject(user_id)
    gaps = competencies.identify_gaps(user_id)

    return jsonify({
        "user_id": user_id,
        "due_count": due_count,
        "learning_count": learning_count,
        "total_count": total_count,
        "hard_question_count": len(hard_questions),
        "hard_questions": hard_questions,
        "hard_chapters_by_subject": hard_chapters_by_subject,
        "heatmap": stats.heatmap(user_id),
        "streak": stats.streak(user_id),
        "gap_count": len(gaps),
        "top_gap": gaps[0] if gaps else None,
        "xp": gamification.user_xp(user_id),
    })


@app.route("/api/upload_content", methods=["POST"])
@auth.login_required
def upload_content():
    user = auth.current_user()
    text = request.form.get("text", "")
    file = request.files.get("file")
    subject = request.form.get("subject", "").strip()
    chapter = request.form.get("chapter", "").strip()
    provider = "openrouter"

    api_key = generate.resolve_api_key(provider)
    if not api_key:
        return jsonify({
            "success": False,
            "error": "No AI API key configured. Ask an admin to set one under Admin -> "
                     "AI Settings, or set OPENROUTER_API_KEY as an environment variable.",
        }), 400

    file_text = generate.extract_file_text(file)
    taxonomy = competencies.load_competency_taxonomy()
    prompt = generate.build_prompt(text, file_text, subject=subject, chapter=chapter, competencies=taxonomy)

    try:
        if provider == "openrouter":
            questions = generate.generate_questions_openrouter(
                prompt=prompt,
                api_key=api_key,
                model=request.form.get("model", "openrouter/free"),
            )
        elif provider == "openai":
            questions = generate.generate_questions_openai(
                prompt=prompt,
                api_key=api_key,
                model=request.form.get("model", "gpt-4o-mini"),
            )
        else:
            return jsonify({"success": False, "error": "Invalid provider"})
    except requests.HTTPError as e:
        print(f"OpenRouter error body: {e.response.text}")
        return jsonify({"success": False, "error": str(e)}), 502
    except (json.JSONDecodeError, KeyError) as e:
        return jsonify({"success": False, "error": f"Failed to parse model response: {e}"}), 500

    # Officers/admins add to the shared OSS bank; students get a private deck.
    is_shared = user["role"] in ("officer", "admin")
    owner_id = None if is_shared else user["id"]
    visibility = "shared" if is_shared else "private"

    saved = []
    for q in questions:
        front = q.get("question", "")
        back = q.get("answer", "")
        options = q.get("options")
        correct_index = q.get("correct_index")
        competency = q.get("competency", "general")
        explanation = q.get("explanation")
        if front and back:
            saved_q = save_question(None, front, back, subject, chapter, competency,
                                     options, correct_index, explanation, owner_id, visibility)
            if saved_q:
                saved.append(saved_q)

    return jsonify({"success": True, "generated": len(saved), "questions": saved, "visibility": visibility}), 200


# ── Share links ──────────────────────────────────────────────────────────

@app.route("/api/share", methods=["POST"])
@auth.login_required
def create_share():
    """Mint a public, no-login link for a set of questions the caller can
    already see (their own private deck, or the shared bank)."""
    data = request.get_json(silent=True) or {}
    question_ids = data.get("question_ids")
    title = (data.get("title") or "").strip()

    user_id = get_user_id()
    visible_ids = {q["id"] for q in load_questions(user_id)}

    if not question_ids:
        # No explicit selection -> share everything the caller owns/authored.
        question_ids = [
            q["id"] for q in load_questions(user_id)
            if q.get("owner_id") == user_id
        ] or list(visible_ids)

    question_ids = [qid for qid in question_ids if qid in visible_ids]
    if not question_ids:
        return jsonify({"error": "No visible questions to share"}), 400

    token = sharing.create_share(user_id, question_ids, title)
    return jsonify({"token": token, "url": f"/share.html?token={token}"}), 201


@app.route("/api/share/<token>", methods=["GET"])
def get_share(token):
    """Public — deliberately no @auth.login_required. Read-only, anonymous."""
    share = sharing.resolve_share(token)
    if share is None:
        return jsonify({"error": "This share link is invalid or has expired"}), 404

    all_questions = {q["id"]: q for q in load_questions(None)}
    questions = [all_questions[qid] for qid in share["question_ids"] if qid in all_questions]
    owner = auth.get_user(share["owner_id"])

    return jsonify({
        "title": share.get("title") or "Shared quiz",
        "shared_by": owner["name"] if owner else "A Gamified Learning user",
        "questions": questions,
    })


# ── Leaderboard ──────────────────────────────────────────────────────────

@app.route("/api/leaderboard", methods=["GET"])
@auth.login_required
def get_leaderboard():
    return jsonify({
        "leaderboard": gamification.leaderboard(),
        "me": gamification.user_xp(get_user_id()),
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)
