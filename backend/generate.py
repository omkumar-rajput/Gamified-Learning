import io
import json
import os
import requests

from backend import settings

# Env var names checked per provider, in resolve_api_key().
_ENV_KEYS = {
    "openrouter": ["OPENROUTER_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
}


def resolve_api_key(provider: str = "openrouter") -> str | None:
    """API key precedence: Admin Settings (DB, set at runtime, no redeploy)
    -> environment variable (Render dashboard) -> local `api-key` file
    (legacy, local-dev only). Returns None if nothing is configured."""
    db_key = settings.get_setting("ai_api_key")
    if db_key:
        return db_key

    for env_name in _ENV_KEYS.get(provider, []):
        value = os.environ.get(env_name)
        if value:
            return value

    try:
        with open("api-key") as f:
            file_key = f.read().strip()
            if file_key:
                return file_key
    except FileNotFoundError:
        pass

    return None


def extract_file_text(file) -> str:
    """
    Extract plain text from an uploaded file.

    Uses pdfminer for PDFs and UTF-8 decoding for plain text files.
    """
    if file is None:
        return ""

    filename = getattr(file, "filename", None) or getattr(file, "name", "")
    filename = filename.lower()
    raw = file.read()
    if isinstance(raw, str):
        raw = raw.encode("utf-8", errors="replace")
    is_pdf = filename.endswith(".pdf") or raw[:5] == b"%PDF-"

    PLAIN_TEXT_EXTENSIONS = (".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml")
    if filename.endswith(PLAIN_TEXT_EXTENSIONS):
        return raw.decode("utf-8", errors="replace").strip()

    if is_pdf:
        return _extract_pdf_text_pdfminer(raw)

    return raw.decode("utf-8", errors="replace").strip()


def _extract_pdf_text_pdfminer(raw: bytes) -> str:
    try:
        from pdfminer.high_level import extract_text
    except ImportError:
        return ""

    try:
        with io.BytesIO(raw) as bio:
            text = extract_text(bio)
    except Exception:
        return ""

    return text.strip() if text else ""


def build_prompt(
    text: str,
    file_text: str,
    subject: str = "",
    chapter: str = "",
    competencies: list[dict] | None = None,
) -> str:
    """Build the user prompt sent to the model. Produces MCQs, each tagged
    with the closest-matching competency from the OSS competency taxonomy."""
    parts = []
    if subject:
        parts.append(f"=== Subject ===\n{subject}")
    if chapter:
        parts.append(f"=== Chapter ===\n{chapter}")
    if text:
        parts.append(f"=== Pasted text ===\n{text}")
    if file_text:
        parts.append(f"=== File content ===\n{file_text}")

    combined = "\n\n".join(parts) if parts else "(no content provided)"

    competency_list = ""
    if competencies:
        ids = ", ".join(f'"{c["id"]}" ({c["name"]})' for c in competencies)
        competency_list = (
            "Assign each question to the single best-fitting competency id from this list: "
            f"{ids}. If none fit well, use \"general\".\n"
        )

    return (
        "You are an expert exam-item writer for the capacity-building programme of "
        "India's Official Statistical System (Ministry of Statistics and Programme "
        "Implementation). Based on the content below, write multiple-choice questions "
        "(MCQs) that test understanding of the key concepts. Generate as many distinct "
        "questions as needed to cover the material without repetition.\n\n"
        f"{competency_list}"
        "Return ONLY a valid JSON array (no markdown fences, no prose) where each element "
        "is an object with exactly these keys:\n"
        '  "question": string,\n'
        '  "options": an array of exactly 4 distinct strings (one correct, three plausible distractors),\n'
        '  "correct_index": integer 0-3, the index into "options" of the correct answer,\n'
        '  "competency": string, one of the competency ids listed above (or "general"),\n'
        '  "explanation": a 1-2 sentence explanation of why the correct answer is right '
        "and, briefly, why the closest distractor is wrong,\n\n"
        f"{combined}"
    )


def parse_questions(raw_text: str) -> list:
    """Parse the model's JSON response, stripping markdown fences if present."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        if "```" in text:
            text = text[: text.rindex("```")]
    return json.loads(text.strip())


def _normalize_mcq(item: dict) -> dict:
    """Ensure a generated item has the shape the app expects, and derive a
    flashcard-style 'answer' string for backward-compatible display."""
    options = item.get("options") or []
    correct_index = item.get("correct_index")
    answer = ""
    if isinstance(options, list) and isinstance(correct_index, int) and 0 <= correct_index < len(options):
        answer = options[correct_index]
    return {
        "question": item.get("question", ""),
        "answer": answer,
        "options": options if options else None,
        "correct_index": correct_index if options else None,
        "competency": item.get("competency") or "general",
        "explanation": item.get("explanation") or "",
    }


def generate_questions_openai(prompt: str, api_key: str, model: str = "gpt-4o-mini") -> list:
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "temperature": 0.7,
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful assistant that always responds with valid JSON.",
            },
            {"role": "user", "content": prompt},
        ],
    }

    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()

    raw = response.json()["choices"][0]["message"]["content"]
    return [_normalize_mcq(item) for item in parse_questions(raw)]


def generate_questions_openrouter(
    prompt: str,
    api_key: str,
    model: str = "openai/gpt-4o-mini",
    site_url: str = "",
    site_name: str = "",
) -> list:
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        **({"HTTP-Referer": site_url} if site_url else {}),
        **({"X-Title": site_name} if site_name else {}),
    }
    payload = {
        "model": model,
        "temperature": 0.7,
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful assistant that always responds with valid JSON.",
            },
            {"role": "user", "content": prompt},
        ],
    }

    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()

    raw = response.json()["choices"][0]["message"]["content"]
    return [_normalize_mcq(item) for item in parse_questions(raw)]
