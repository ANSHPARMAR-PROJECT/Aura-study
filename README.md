# AURA Study

AURA Study is an adaptive academic planner evolved from the supplied StudyPulse AI project. This starter preserves the original Flask/Python backend conventions, enrolled-course model, manual study-hour logging, recommendation behavior, and legacy SQLite table names while adding JWT authentication, a React dashboard, and the core AURA workflows.

## Included in this version

- Premium cream / forest-green / lavender dashboard with responsive layouts.
- React + Vite + Tailwind CSS, Framer Motion, Zustand, Recharts, Lucide icons, and dnd-kit.
- Flask REST API with SQLAlchemy models.
- User registration, login, logout, 12-hour HTTP-only JWT access cookies, ownership checks, CSRF protection on authenticated write requests, and password hashing.
- Enrolled courses, exam dates, difficulty, target hours, manual study-hour logging, and progress chart.
- Projects with create/edit/delete, project tasks with create/edit/delete and due dates, task completion, customizable project tags, and progress calculated from tasks.
- Enrolled courses with create/edit/delete, exam dates, difficulty, and target-hour tracking.
- Date-selectable daily schedule blocks with create/edit/delete, server-side overlap detection, linked courses/projects, and draggable AI suggestions.
- Pomodoro focus timer that persists across frontend navigation and refreshes using timestamps; completed focus sessions are logged idempotently and saved durations are configurable.
- Settings page for profile details, focus/break lengths, daily study target, preferred focus window, cream/night theme, and reminder preference.
- Rule-based adaptive recommendations plus optional Gemini enhancement.
- Resource Bank for file uploads and web links (10 MB maximum; owner-only downloads).
- SQLite by default for local development; PostgreSQL supported by setting `DATABASE_URL`.
- Basic API smoke tests.

## Technology choices

| Layer | Implementation |
|---|---|
| Frontend | React 18 + Vite |
| Styling | Tailwind CSS + custom CSS variables |
| Motion | Framer Motion |
| State | Zustand with persisted timer state |
| Drag & drop | dnd-kit |
| Charts | Recharts |
| Backend | Python + Flask |
| ORM / database | SQLAlchemy 2 + SQLite (default) / PostgreSQL |
| AI | Deterministic study-priority engine + optional Google Gemini |

## Run locally on Windows

You need Python 3.10+ and Node.js 18+.

### 1. Configure the backend

Open PowerShell in the `aura-study` folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
```

Open `backend/.env` and set a private random `FLASK_SECRET_KEY`. A quick way to generate one is:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

You may leave `GEMINI_API_KEY` blank initially. The built-in recommendation engine works without an AI key.

### 2. Start the Flask API

In the first PowerShell terminal:

```powershell
cd backend
python app.py
```

The API listens at `http://127.0.0.1:5000`.

### 3. Start the React frontend

Open a second PowerShell terminal in the project folder:

```powershell
cd frontend
npm install
npm run dev
```

Open the Vite URL printed in the terminal (normally `http://127.0.0.1:5173`). The Vite development server proxies `/api` requests to Flask, so the session cookie remains same-origin from the browser's perspective.

## Production-style frontend build

From `frontend`:

```powershell
npm install
npm run build
```

Then start Flask from `backend` with `FLASK_ENV=production`, a strong `FLASK_SECRET_KEY`, and `COOKIE_SECURE=true` behind HTTPS. Flask serves the compiled React app from `frontend/dist` when that directory exists.

## PostgreSQL (optional)

SQLite is intentionally the zero-configuration default. To use PostgreSQL, create a database and set this in `backend/.env`:

```env
DATABASE_URL=postgresql+psycopg://aura_user:your_password@localhost:5432/aura_study
```

The included requirements install the Psycopg 3 driver. Restart Flask after changing the database URL. For an existing production database, use a migration tool such as Alembic before deploying schema changes.

## Gemini setup (optional)

Add your Google AI Studio API key to `backend/.env`:

```env
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-3.5-flash-lite
```

Restart Flask. AURA first creates a deterministic recommendation set from course deadlines, difficulty, remaining hours, revision gaps, and recorded focus sessions. Gemini is an optional wording/insight enhancement; an API outage, missing package, or invalid model response falls back to the deterministic engine.

## Existing StudyPulse data

The uploaded ZIP did not contain a database file. If your local old project has `study_planner.db`, copy it into the `backend` folder before the first launch. The models retain the original `users`, `subjects`, and `study_logs` table names and column layout. If you leave the old database one folder above `backend`, the app attempts to copy it into `backend` automatically when the new database file does not yet exist.

Do not copy the old `.env` file. Create a new `backend/.env` from `.env.example`, generate a new secret, and keep API keys out of ZIP files and source control.

## Tests

After installing backend requirements, run from the project root:

```powershell
pip install pytest
python -m pytest backend\tests -q
```

The tests cover course registration and logging, course editing, task due dates, schedule editing and overlap rejection, preferences/profile updates, timer idempotency and user-scoped session keys, plus AI recommendation slot and priority behavior.

## Important implementation notes / next steps

This is a runnable MVP foundation, not a finished production deployment. Before public deployment, add Alembic migrations, login rate limiting, email verification/password reset, automated frontend tests, monitoring, backups, and a stricter content-security policy. The `AIRecommendations` table is present as an extension point; persisted AI feedback is not yet wired into the UI/API. Reminder preferences are stored, but browser/push reminder delivery is not implemented yet.

The schedule stores local wall-clock times from the browser. For multi-time-zone deployments, add an explicit user timezone preference and normalize event times to UTC.

## Phase 1 upgrades (November 2026)

This release completes the existing workspace management flows without changing
its React + Flask + SQLAlchemy architecture:

- Edit enrolled courses (name, exam date, difficulty, and target hours).
- Edit and delete project tasks; add and edit task due dates.
- Edit schedule blocks, including time, type, linked project, and linked course.
  The API continues to reject overlapping blocks, including edits that would
  conflict with another event.
- Update the student username and email from Settings.
- Configure focus, short-break and long-break durations, daily study target,
  preferred focus window, workspace theme, and reminder preference.
- Use the saved preferred focus window when AURA selects free slots for its
  daily recommendations.

On startup, AURA adds the new `theme` and `notifications_enabled` preference
columns to an existing `user_preferences` table if they are missing. Existing
course, project, task, and study records are preserved. Back up
`backend/study_planner.db` before upgrading an existing installation.

The reminder preference is stored now for the future reminder feature; this
release does not send browser or push notifications.

## Phase 2 — Intelligent Learning Hub (November 2026)

Phase 2 adds a dedicated Learning Hub while keeping the React + Flask + SQLAlchemy stack and existing Phase 1 tables intact. New tables are created non-destructively by SQLAlchemy `create_all()`:

- **Adaptive daily plan:** builds proposed study blocks using exam proximity, course difficulty, remaining course target hours, unfinished project tasks and their due dates, recent manual study logs, the saved focus window, and existing schedule events. The user reviews the plan before applying it. The API rechecks conflicts immediately before inserting the blocks.
- **Active Recall Quizzer:** generates multiple-choice quizzes from student-provided notes. When `GEMINI_API_KEY` is configured, Gemini creates and validates the questions. Without Gemini, the offline generator uses explicit `Term: definition` lines and never invents facts from a course title. Quiz answers are held on the server until submission. Attempts are saved with scores and explanations.
- **Flashcards:** creates cards from notes using Gemini or offline `Term: definition` lines, and supports manual cards. Reviews use a transparent Again / Hard / Good / Easy interval scheduler. Only due cards appear in the practice queue.
- **Revision tracker:** supports manually scheduled revisions and automatic next-day reminders when a course-linked quiz result is below 70%. Revision reminders can be completed, reopened, edited, or deleted.

### Offline note format

If you have not configured Gemini, write at least two note lines in this format:

```text
Osmosis: Movement of water across a selectively permeable membrane.
Mitosis: Cell division that produces two genetically identical daughter cells.
Chloroplast: An organelle where photosynthesis takes place.
```

The fallback quiz and flashcard generators use only these explicit pairs. For ordinary paragraph notes, configure `GEMINI_API_KEY` in `backend/.env` and restart Flask.

### Phase 2 API routes

- `GET /api/learning/overview`
- `GET /api/learning/daily-plan?date=YYYY-MM-DD`
- `POST /api/learning/daily-plan/apply`
- `POST /api/learning/quizzes/generate`
- `GET /api/learning/quizzes`
- `GET /api/learning/quizzes/:id`
- `POST /api/learning/quizzes/:id/attempts`
- `GET /api/learning/flashcards?due_only=true`
- `POST /api/learning/flashcards`
- `POST /api/learning/flashcards/generate`
- `PATCH /api/learning/flashcards/:id/review`
- `DELETE /api/learning/flashcards/:id`
- `GET /api/learning/revisions`
- `POST /api/learning/revisions`
- `PATCH /api/learning/revisions/:id`
- `DELETE /api/learning/revisions/:id`

New learning records are scoped to the authenticated user. Existing course, project, schedule, timer, and resource records are not dropped or renamed. Back up `backend/study_planner.db` before upgrading.

### Phase 2 tests

Run from the project root:

```powershell
python -m pytest backend\tests -q
```

The added test coverage includes offline quiz and flashcard generation, spaced-repetition intervals, schedule-aware daily planning, applying generated plans, quiz submission, and revision tracking.


## Phase 3 — Student Productivity

Phase 3 adds a Productivity workspace while preserving Phase 1 and Phase 2 data. New SQLAlchemy tables are created automatically on startup; the existing users, courses, projects, study logs, timer sessions, quizzes, flashcards, and revision records are not renamed or removed.

### Included functionality

- 7-, 30-, and 90-day study analytics with daily hours and focus-session counts.
- A 70-day activity heatmap, current/longest streaks, course study-hour breakdown, and focus-session start-time pattern.
- Daily study-goal progress using the saved `daily_goal_hours` preference.
- Persistent achievements for focus sessions, study-hour milestones, streaks, quiz completions, and goal consistency.
- Notification center with deduplicated upcoming-exam and project-task deadline notifications.
- Personal reminders that are surfaced in AURA while the app is open. The frontend polls once per minute; reminders are not push notifications and will not appear if the browser/app is closed.

### New API endpoints

- `GET /api/productivity/overview?days=7|30|90` — analytics, heatmap, goals, insights, achievements, and unread count.
- `GET /api/productivity/notifications` — list notifications and sync upcoming exam/task alerts.
- `PATCH /api/productivity/notifications/<id>/read` — mark one notification read.
- `POST /api/productivity/notifications/read-all` — mark all notifications read.
- `DELETE /api/productivity/notifications/<id>` — remove a notification.
- `GET /api/productivity/reminders` — list personal reminders.
- `POST /api/productivity/reminders` — create a personal reminder.
- `GET /api/productivity/reminders/due` — deliver due reminders to the in-app notification center.
- `PATCH /api/productivity/reminders/<id>` — update reminder status.
- `DELETE /api/productivity/reminders/<id>` — delete a reminder.

### Test

From the project root, run `python -m pytest backend\tests -q`. The Phase 3 API regression tests are in `backend/tests/test_productivity.py`.

## Phase 4 — Advanced Platform

Phase 4 adds calendar portability, authenticated study-group collaboration, and a richer Resource Bank while preserving Phase 1–3 tables and existing student data.

### Calendar export and Google Calendar import

- `GET /api/calendar/export?start=YYYY-MM-DD&end=YYYY-MM-DD&timezone=Asia/Kolkata` exports the signed-in user's scheduled blocks as an iCalendar (`.ics`) file.
- The default window is today through the next 90 days; exports are limited to 366 days.
- The frontend Schedule page includes an Export `.ics` action and a link to Google Calendar's import settings.
- Import the downloaded `.ics` file in Google Calendar Settings → Import & export → Import.
- This is a one-way snapshot export/import, not automatic two-way Google Calendar synchronization or OAuth connection.

### Study Groups

- `GET /api/groups` lists groups the signed-in user belongs to.
- `POST /api/groups` creates a group and owner membership; the response includes an invite code.
- `POST /api/groups/join` joins with an invite code.
- `GET /api/groups/:id` returns group details, members and recent updates, only for members.
- `POST /api/groups/:id/posts` posts an update and can share one resource from the author's Resource Bank.
- `DELETE /api/groups/:id/posts/:post_id` removes an update for its author or group owner.
- `DELETE /api/groups/:id/members/me` lets a member leave; group owners delete their group with `DELETE /api/groups/:id`.
- `GET /api/groups/:id/resources/:resource_id/download` allows a current group member to download a file that has been shared in that group.

Groups are private to their members. Classmates must use accounts on the same AURA deployment/database. Invite codes should be shared privately.

### Resource Bank improvements

- Resources now have a description, category, detected MIME type, file size and updated timestamp.
- `PATCH /api/resources/:id` updates a resource's title, description, category and linked project.
- `GET /api/resources/:id/preview` serves owned PDF and image resources inline for the in-app preview modal.
- Existing `GET /api/resources/:id/download` and `DELETE /api/resources/:id` remain available and user-scoped.
- The Resource Bank UI adds category filtering, full-text-style title/filename/description search, editing, PDF/image preview, and file metadata.
- Existing `resources` tables are upgraded using additive `ALTER TABLE` statements; existing resource rows and files are preserved.

### Phase 4 verification

Run from the project root:

```powershell
python -m pytest backend\tests -q
cd frontend
npm run build
```

Phase 4 regression coverage is in `backend/tests/test_phase4.py` and checks group creation/join/member access, shared-file access control, resource metadata updates and ownership, and calendar export validation/content.

## Phase 5 — Production Readiness (November 2026)

Phase 5 hardens the existing application while keeping the React + Flask + SQLAlchemy architecture and all Phase 1–4 data models.

### Security and reliability improvements

- **Strong signing secret:** `FLASK_SECRET_KEY` must be at least 32 UTF-8 bytes. Generate one with `python -c "import secrets; print(secrets.token_hex(32))"`. Changing it invalidates existing login cookies, so users must sign in again.
- **JWT time handling:** JWT `iat` and `exp` claims are timezone-aware UTC values. SQLAlchemy's legacy UTC timestamps use a timezone-aware clock converted to naive UTC for compatibility with existing `DateTime` columns.
- **Database-backed rate limiting:** Login (8 attempts per 5 minutes per IP), registration (5 attempts per hour per IP), quiz/flashcard generation (12 per minute per account), and group joining (10 per hour) are limited. Only salted-by-hash bucket identifiers are stored; raw IP addresses are not persisted. The counters are shared across app workers through SQLite/PostgreSQL.
- **Security headers:** CSP (including the existing Google Fonts stylesheet/font hosts and same-origin PDF previews), `X-Content-Type-Options`, same-origin framing protection, `Referrer-Policy`, `Permissions-Policy`, no-store API responses, and HSTS in production.
- **Host/proxy controls:** Production host allow-list through `AURA_ALLOWED_HOSTS`; optional `ProxyFix` only when `TRUSTED_PROXY_COUNT` is explicitly configured.
- **Operational health:** Unauthenticated `GET /api/health` returns a minimal service/database status for health checks.
- **Operational logs:** Backend request logs include request ID, method, route, status, and duration. Local development logs rotate at 2 MB with five retained files under `backend/logs/`; production logs go to stderr for Gunicorn/container collection. Request bodies, passwords, and API keys are not logged.
- **Backups:** `python backend/scripts/backup_database.py` makes a consistent SQLite backup using SQLite's backup API or a PostgreSQL custom-format backup using `pg_dump`.
- **Database migrations:** Alembic is configured. New installs can run `alembic upgrade head`; it only creates missing tables and does not drop existing rows. Local development continues to use additive `init_db()` behavior with `AUTO_CREATE_DB=true`.
- **Production server/deployment files:** Waitress is available for Windows; Gunicorn is used in the Linux Docker image. A multi-stage Dockerfile, production Compose file, and example Nginx HTTPS reverse-proxy configuration are included.
- **Bundle splitting:** Vite now separates React, charting, animation, icon, drag-and-drop, and remaining vendor modules into build chunks to reduce the single large JavaScript chunk.

### Update your existing Phase 4 installation

1. Stop the Flask and Vite terminals.
2. Back up `backend/.env`, `backend/study_planner.db`, and the whole `backend/uploads/` folder.
3. Copy the Phase 5 patch source files into the existing project. Keep `.env`, the database, uploaded resources, `frontend/node_modules/`, and `frontend/package-lock.json`.
4. Generate a new strong key and replace the current `FLASK_SECRET_KEY` in `backend/.env`. This signs out existing sessions; it does not delete account or study records.
5. Install the two new backend package groups with `python -m pip install -r backend/requirements.txt` (Alembic and Waitress; Gunicorn installs only on non-Windows platforms).
6. Run `python -m pytest backend\\tests -q` and `cd frontend; npm install; npm run build`.
7. Restart Flask and Vite for local development.

### Local backup and verification commands (Windows PowerShell)

Run from the project root with the virtual environment activated:

```powershell
python backend/scripts/backup_database.py
python backend/scripts/verify_database.py
python -m pytest backend\\tests -q
```

Backups are written to `backend/backups/` by default. Copy these backup files to a separate drive or secure cloud storage; a backup on the same disk does not protect against disk failure. For PostgreSQL, install PostgreSQL client tools so `pg_dump` is on PATH. Schedule the backup script with Windows Task Scheduler for unattended daily backups.

### Alembic workflow

For local development, keep `AUTO_CREATE_DB=true` (the default) so AURA safely creates missing tables and applies the existing Phase 1–4 additive compatibility changes.

For a production database, back it up first, run `alembic upgrade head` from the project root, and then set `AUTO_CREATE_DB=false`. The baseline migration creates missing mapped tables without dropping or renaming existing data. Future schema changes should be added as new Alembic revisions; do not manually edit old applied revisions.

### Production deployment checklist

- Set `FLASK_ENV=production`, `FLASK_DEBUG=false`, `COOKIE_SECURE=true`, and `AUTO_CREATE_DB=false`.
- Set `FLASK_SECRET_KEY` to a unique random value of at least 32 bytes. Do not reuse development or test keys.
- Set `AURA_ALLOWED_HOSTS` to the exact public host names (comma-separated; no URL scheme or path).
- Set `TRUSTED_PROXY_COUNT=1` only when exactly one trusted reverse proxy sits in front of Flask. Otherwise leave it `0`.
- Use PostgreSQL for multi-instance deployments; keep credentials in environment secrets, not Compose files or Git.
- Serve through HTTPS. The production Compose file binds the app to localhost so a TLS reverse proxy can expose it.
- Keep `backend/.env`, uploads, backups, and logs out of source control and public web roots.
- Configure scheduled database backups and test restoring them before onboarding real users.
- Run `python backend/scripts/verify_database.py` and check `GET /api/health` after deployment.

The included production Compose file expects `POSTGRES_PASSWORD` and `AURA_ALLOWED_HOSTS` to be supplied by the deployment environment. The Nginx example uses placeholder domain/certificate paths that must be replaced before deployment.

### Phase 5 tests

New tests cover the health endpoint, baseline security headers, request IDs, and database-backed login rate limiting. Run all Phase 1–5 backend tests with:

```powershell
python -m pytest backend\\tests -q
```

The Vite build uses explicit manual chunks; check its output for any remaining chunk warnings. A successful build is required, while chunk warnings are performance advisories rather than compilation failures.
