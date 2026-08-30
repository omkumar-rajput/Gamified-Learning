# Gamified Learning — Statistical Capacity-Building Platform (SIH26101)

An AI-enabled learning platform for India's Official Statistical System (OSS)
that identifies competency gaps, recommends personalized training linked to
iGOT Karmayogi, and generates MCQs from uploaded learning material — built on
an FSRS (Free Spaced Repetition Scheduler) engine for durable retention.

**One platform, two audiences, one AI engine.** Official OSS officers get
competency-gap-driven, iGOT-linked capacity building (admin-provisioned
accounts, shared question bank, org-wide dashboard). Anyone else — students,
new recruits, self-learners — can self-serve: sign up, upload material, get
an AI-generated quiz instantly, and hand out a public share link with no
login required on the other end.

## Feature list

- **Real auth + roles.** Session-based login, three roles: `admin` (full
  control — the only role that can create officer/admin accounts), `officer`
  (shared OSS question bank, competency/iGOT view), `student` (public
  self-signup, private decks). No more persona switcher.
- **Student self-serve decks.** Upload text/PDF → private, AI-generated MCQ
  deck with its own FSRS schedule, invisible to other users unless shared.
- **Public share links.** Any deck owner mints a no-login `/share.html?token=`
  link — hand it to a judge/friend, they can take the quiz immediately.
- **AI-generated "why" explanations** on every MCQ, shown after answering.
- **Gamification** — XP per review (weighted by how well you recalled it),
  levels, and an opt-out leaderboard.
- **Admin AI Settings** — paste/rotate the AI API key from the running app;
  no redeploy needed.
- **Dark/light theme** (persisted) + motion: page transitions, card-enter
  animation, confetti on correct answers and level-ups, animated stat counts.
- Everything from the original build still works as-is: FSRS flashcards/MCQs,
  competency-gap radar, GitHub-style contribution heatmap, hardest-questions
  list, iGOT course recommendations, and the question Manage/Edit page.

## How to run locally

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then open `http://127.0.0.1:5000`. Log in with a seeded demo account (shown
on the login page) or sign up as a new student.

**Demo accounts** (password `demo1234` for all — change/remove before a real
deployment):

| Name | Email | Role |
|---|---|---|
| Priya Sharma | `priya@demo.oss.gov.in` | officer |
| Arjun Mehta | `arjun@demo.oss.gov.in` | officer |
| Training Manager | `admin@demo.oss.gov.in` | admin |

Each demo officer has ~50 days of simulated FSRS review history baked into
`data/cards.json` / `data/review_log.json`, so the dashboard, competency
radar, and recommendations are populated out of the box.

### Environment variables (all optional for local dev)

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Signs the session cookie. Set a real random value in production. |
| `ADMIN_BOOTSTRAP_EMAIL` / `ADMIN_BOOTSTRAP_PASSWORD` | Creates one extra admin account on first boot (in addition to the seeded demo admin). |
| `OPENROUTER_API_KEY` / `OPENAI_API_KEY` | AI key for MCQ generation — see below. |

## Adding the AI API key

MCQ generation from uploads needs an AI key (OpenRouter or OpenAI). There
are three ways to supply one, checked in this order:

1. **Fastest — Admin → AI Settings**, in the running app. Log in as an
   admin, open the Admin page, paste the key under "AI Settings", save.
   Takes effect immediately, no restart.
2. **Environment variable** — set `OPENROUTER_API_KEY` (or `OPENAI_API_KEY`)
   in your shell locally, or in the Render dashboard's Environment tab for a
   deployed instance.
3. **Legacy local file** — create a file named `api-key` in the project root
   containing the key (git-ignored). Local dev convenience only; doesn't
   work on Render (ephemeral build, no way to hand-place a file).

Without any of these, Upload returns a clear error; the rest of the app
(quiz, dashboard, competency tracking, recommendations, admin view) works
fully off the bundled 30-question demo bank regardless.

## Deploying to Render

Render only — see "Why not Vercel" below. Two ways to deploy:

**A. Blueprint (recommended)** — this repo includes `render.yaml`. In the
Render dashboard: **New → Blueprint**, point it at this repo, review the
plan, deploy. It provisions one web service with a 1GB persistent disk
mounted at `data/` (so the SQLite user store and JSON question/card files
survive restarts and redeploys) and prompts for the env vars below.

**B. Manual web service:**

1. **New → Web Service**, connect this repo.
2. Build command: `pip install -r requirements.txt`
3. Start command: `gunicorn app:app`
4. Add a **persistent disk**, mount path `data` (or the absolute path Render
   shows for your service's working directory + `/data`), size 1GB.
5. Environment variables: `SECRET_KEY` (generate a random string),
   `ADMIN_BOOTSTRAP_EMAIL` + `ADMIN_BOOTSTRAP_PASSWORD` (your real admin
   login for the deployed instance), `OPENROUTER_API_KEY` (or set it later
   from Admin → AI Settings instead).
6. Deploy. First boot seeds the demo accounts + your bootstrap admin.

### Why not Vercel

Vercel runs Flask as short-lived serverless functions with an ephemeral
filesystem — every cold start gets a fresh disk, so the SQLite user store,
uploaded question bank, and FSRS card state would all silently reset. Render
gives this app a normal always-on process with a real persistent disk, which
is what a stateful Flask + SQLite app needs. Don't deploy this to Vercel as-is.

## Architecture

```
app.py                      Flask routes (auth, admin, questions, share, leaderboard)
Procfile / render.yaml       Render deploy config
backend/
  auth.py                    SQLite users, sessions, roles, login/admin_required
  settings.py                Runtime-editable settings (AI key), same SQLite file
  gamification.py            XP, levels, leaderboard
  sharing.py                 Public share-link tokens
  scheduler.py               FSRS scheduling, per-user cards & review log, question visibility
  stats.py                   Streaks, heatmap, "hardest questions"
  competencies.py            Competency-gap scoring (coverage + accuracy + retention)
  mock_igot.py               Mock iGOT Karmayogi course catalog + recommender
  generate.py                LLM-based MCQ generation + API key resolution
data/
  app.db                     SQLite: users, settings (git-ignored)
  questions.json             Shared + private MCQ bank (30 seeded questions, 6 competencies)
  xp.json / shares.json      Gamification + share-link state
  competencies.json          OSS competency taxonomy
  igot_catalog.json          Mock iGOT course catalog, keyed by competency
  cards.json / review_log.json   Per-user FSRS state (nested by user_id)
frontend/
  login.html / signup.html    Real auth (replaces the old persona switcher)
  index.html                  Dashboard: stats, competency radar, gap preview
  quiz.html / quiz.js         MCQ + flashcard review flow, explanations, XP toast
  learning-path.html          Ranked competency gaps + iGOT course recommendations
  upload.html                 Upload material → AI-generated deck → share link
  edit.html                   Manage questions (competency, subject, chapter, MCQ options)
  admin.html                  Org competency overview + Manage People + AI Settings
  leaderboard.html            XP leaderboard
  share.html                  Public, no-login quiz view for a shared deck
  common.js                   Auth/session helper, theme toggle, XP toast, confetti
```

## How this maps to SIH26101

| PS requirement | Where it lives |
|---|---|
| Generate quizzes/MCQs from uploaded material | `backend/generate.py`, `upload.html` |
| Identify competency gaps | `backend/competencies.py`, dashboard radar chart |
| Recommend personalized training | `backend/mock_igot.py`, `learning-path.html` |
| Integrate with iGOT Karmayogi | `backend/mock_igot.py` (mocked catalog + deep-link pattern; see module docstring for how to swap in the real API) |
| Capacity building across the OSS | `admin.html` — aggregate competency view + officer provisioning |

## Known limitations (be upfront about these in the demo)

- iGOT Karmayogi integration is **mocked** — no live API/SSO access was
  available. The connector module is structured so a real integration only
  requires replacing `load_igot_catalog()`.
- Competency scoring is a transparent heuristic (documented in
  `backend/competencies.py`), not a validated psychometric model.
- Demo accounts share a well-known password (`demo1234`) — fine for a
  hackathon walkthrough, rotate/remove before any real deployment.
