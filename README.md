# Guess the Word

A web-based word-guessing game and administrative reporting platform built with **Python**, **FastAPI**, **SQLAlchemy 2.x**, **SQLite**, and **Vanilla JavaScript/CSS** for the OpenText pre-internship project.

Players have 5 attempts to guess a secret five-letter English word, with a daily limit of 3 games per calendar day. Administrators can view daily system usage and per-user activity reports.

---

## Features

- **Wordle-Style Gameplay**: 5-letter word puzzle with 5 attempts per game and real-time colored tile feedback.
- **Duplicate Letter Accounting**: Two-pass evaluation prevents over-counting repeated letters in guesses.
- **Strict Daily Limit**: Server enforces a maximum of 3 started games per player per calendar day (UTC).
- **Physical Keyboard Input**: Gameplay is controlled via the player's physical keyboard with animated tile reveals (no on-screen virtual keyboard).
- **Role-Based Access Control**: Public registration creates standard Player accounts; Admin accounts are provisioned via a dedicated CLI utility.
- **Admin Reporting**: Daily aggregate metrics (active players, games won) and per-user activity reports (words tried, games won).
- **Defensive State Exposure**: The target secret word is strictly hidden on the server while a game is active and only revealed upon game completion.
- **Isolated Automated Testing**: 207 automated tests running against an in-memory SQLite database.

---

## OpenText Requirements

| Requirement | Specification | Implementation | Status |
|---|---|---|---|
| **Framework** | Use Python (no Django) | Built with FastAPI, Starlette, and SQLAlchemy 2.x | Verified |
| **User Roles** | Admin and Player roles | `UserRole` enum (`PLAYER`, `ADMIN`) with role-based access control dependencies | Verified |
| **Registration & Login** | Separate registration and login | Server-rendered HTML forms and JSON endpoints (`/register`, `/login`, `/logout`) | Verified |
| **Username Validation** | At least 5 letters, letters only | Validated with `isalpha()` and length $\ge 5$; normalized to lowercase | Verified |
| **Password Rules** | At least 5 characters; letters, digits, and special chars (`$`, `%`, `*`) | Enforced in schemas using regex (`[a-zA-Z]`, `[0-9]`, and `[$%*]`) | Verified |
| **Password Confirmation** | Prevent typos during registration | `confirm_password` field validated before account creation | Verified |
| **Word Repository** | Exactly 20 five-letter English words | 20 uppercase words seeded into the SQLite `words` table | Verified |
| **Random Word Selection** | Random word per game from repository | `random.choice(words)` queries database words on game start | Verified |
| **Daily Game Limit** | Max 3 games per player per day | Server-side count of `Game.started_at` in UTC day; returns HTTP 429 when reached | Verified |
| **Attempt Limit** | Max 5 guesses per game | `MAX_ATTEMPTS = 5`; game status transitions to `LOST` if attempt 5 fails | Verified |
| **Letter Evaluation** | Green (correct), Amber (present), Slate (absent) | Two-pass evaluation with frequency counting for repeated letters | Verified |
| **Guess Persistence** | Record all submitted guesses | Each guess stored in `guesses` table linked to `game_id` and `attempt_number` | Verified |
| **Daily Report** | Users count and correct guesses per date | Aggregates distinct active players and games won for specified UTC date | Verified |
| **Per-User Report** | Date, words tried, and correct guesses per user | Aggregates sessions started and games won for a specific player on a given date | Verified |
| **Testing** | Automated test coverage | 207 tests across 7 test suites using an in-memory SQLite test database | Verified |

*Reporting Definitions:*
- **"Words tried"**: Total game sessions started by a user on that calendar date.
- **"Correct guesses"**: Total game sessions won whose session started on that calendar date.

---

## Technology Stack

- **Backend Framework**: [FastAPI](https://fastapi.tiangolo.com/) (asynchronous routing, dependency injection, validation)
- **Database & ORM**: [SQLAlchemy 2.0](https://www.sqlalchemy.org/) with [SQLite](https://www.sqlite.org/) (`PRAGMA foreign_keys=ON`)
- **Schema Migrations**: [Alembic](https://alembic.sqlalchemy.org/) (schema revision tracking)
- **Templating**: [Jinja2](https://jinja.palletsprojects.com/) (server-side HTML rendering)
- **Frontend**: Vanilla JavaScript and Vanilla CSS; no frontend framework or build system required.
- **Password Hashing**: Argon2id via `pwdlib` and `argon2-cffi`
- **Session Security**: `itsdangerous` (`URLSafeTimedSerializer` signed session cookies)
- **Data Validation & Settings**: `pydantic` v2 and `pydantic-settings`
- **Testing**: `pytest` with Starlette `TestClient`

---

## Architecture

The application follows a clean layered architecture separating HTTP routing, business logic, and data persistence:

```
Browser (Jinja2 Templates + Vanilla JS / CSS)
    ↓  HTTP Requests (Signed Session Cookies)
FastAPI Routes (app/routes/: auth, game, admin)
    ↓  Role & Authentication Dependencies
Service Layer (app/services/: auth, game, report, word_seed)
    ↓  Business Rules & Evaluations
SQLAlchemy 2.x Models (app/models/: User, Word, Game, Guess)
    ↓  Relational Mapping (Foreign Keys ON)
SQLite Database (./data/guesstheword.db)
```

---

## Project Structure

```
GuessTheWord/
├── app/
│   ├── enums/            # System enums: UserRole, GameStatus, LetterEvaluation
│   ├── models/           # SQLAlchemy models: User, Word, Game, Guess
│   ├── routes/           # FastAPI routers: auth.py, game.py, admin.py
│   ├── schemas/          # Pydantic validation schemas: auth, game, report
│   ├── services/         # Business logic: game_service, auth_service, report_service, word_seed
│   ├── static/           # Static CSS and client-side JavaScript
│   ├── templates/        # Jinja2 templates (auth, game, admin, base)
│   ├── config.py         # Application settings via Pydantic
│   ├── create_admin.py   # CLI tool to provision Admin accounts
│   ├── database.py       # Engine, sessionmaker, and UTCDateTime decorator
│   └── main.py           # FastAPI application factory
├── data/                 # SQLite storage (guesstheword.db - not committed)
├── migrations/           # Alembic schema migrations
├── tests/                # Automated pytest suite (207 tests)
├── .env.example          # Sample environment variables
├── alembic.ini           # Alembic migration configuration
├── requirements.txt      # Python dependencies
└── run.py                # Development server runner
```

---

## Database

The database consists of four relational tables managed through SQLAlchemy models and Alembic migrations:

```
User (1) ──────< Game (N) ──────< Guess (N)
                  │
Word (1) ─────────┘
```

- **`users`**: Stores username (lowercase, unique), Argon2id password hash, role (`PLAYER` or `ADMIN`), and creation timestamp.
- **`words`**: Contains the 20 five-letter secret words.
- **`games`**: Tracks player game sessions, assigned secret word, status (`IN_PROGRESS`, `WON`, `LOST`), attempt count, and timestamps.
- **`guesses`**: Persists each 5-letter guess with `attempt_number` and unique constraint `uq_game_attempt_number`.

> **Note**: The SQLite database file (`./data/guesstheword.db`) is generated locally and excluded from Git tracking via `.gitignore`. Each reviewer initializes their own local database.

---

## Authentication & Roles

- **Player Registration**: Public form at `/register`. Requires a unique username (letters only, $\ge 5$ chars), password ($\ge 5$ chars, with letters, digits, and `$`, `%`, or `*`), and matching confirmation password.
- **Password Security**: Passwords are never stored plaintext; they are hashed using Argon2id.
- **Session Handling**: Successful login issues an `HttpOnly`, `SameSite=lax` signed session cookie (`session_token`) valid for 24 hours.
- **Role Enforcement**:
  - `PLAYER`: Can play games and view personal game history.
  - `ADMIN`: Has exclusive access to `/admin/reports` and reporting APIs. Standard players attempting to access admin routes receive `HTTP 403 Forbidden`.

---

## Admin Account Provisioning

Public registration creates standard Player accounts only. Admin accounts must be created using the secure CLI utility:

```powershell
python -m app.create_admin
```

The script prompts for:
1. **Admin username**: Minimum 5 alphabetic characters.
2. **Admin password**: Minimum 5 characters containing letters, numbers, and at least one of `$`, `%`, or `*` (hidden input via `getpass`).
3. **Password confirmation**: Must match the entered password.

---

## Game Mechanics

1. **Word Repository**: Exactly 20 five-letter words (`APPLE`, `BEACH`, `BRAIN`, `BREAD`, `CHAIR`, `CLOUD`, `CRANE`, `DANCE`, `EARTH`, `FLAME`, `FRUIT`, `GHOST`, `GRAPE`, `HEART`, `HOUSE`, `LIGHT`, `MUSIC`, `OCEAN`, `PLANT`, `WATER`).
2. **Random Selection**: When a game starts, a word is chosen randomly from the database via `random.choice(words)`. Consecutive games select independently, so words can occasionally repeat.
3. **Daily Limit**: A player can start at most 3 games per UTC calendar day. Starting a 4th game returns `HTTP 429 Too Many Requests`.
4. **Guess Submission**: Guesses are typed via the physical keyboard and submitted by pressing Enter. Guesses must be exactly 5 alphabetic letters.
5. **Evaluation**:
   - **Green (Correct)**: Letter matches target in both character and position.
   - **Amber (Present)**: Letter exists in target word but in a different position.
   - **Slate (Absent)**: Letter does not exist in remaining target occurrences.
   - *Duplicate letters are accurately counted without over-marking.*
6. **Completion**:
   - **Won**: Guess matches the secret word within 5 attempts.
   - **Lost**: 5 attempts exhausted without guessing the word.
   - The target word is hidden during play and revealed only upon game completion.

---

## Admin Reports

Available to administrators at `/admin/reports`:

1. **Daily Report (`GET /admin/reports/daily?date=YYYY-MM-DD`)**:
   - `number_of_users`: Count of distinct players who started a game on that UTC date.
   - `number_of_correct_guesses`: Count of games won whose session started on that date.
2. **Per-User Report (`GET /admin/reports/user/{user_id}?date=YYYY-MM-DD`)**:
   - `number_of_words_tried`: Game sessions started by this player on that UTC date.
   - `number_of_correct_guesses`: Game sessions won by this player on that date.

---

## Installation & Running

### 1. Clone & Set Up Virtual Environment

```powershell
git clone https://github.com/SunnySatwik/GuessTheWord.git
cd GuessTheWord

python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

*(On macOS/Linux: `source .venv/bin/activate`)*

### 2. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 3. Configure Environment

Copy the sample environment file:

```powershell
Copy-Item .env.example .env
```

*(On macOS/Linux: `cp .env.example .env`)*

### 4. Initialize Database & Seed Words

Run migrations and seed the initial 20 words:

```powershell
alembic upgrade head
python -m app.services.word_seed
```

### 5. Start the Application

```powershell
python run.py
```

The app is now running at **http://127.0.0.1:8000**.

---

## OpenText Reviewer Quick Test

Follow these steps to verify all core requirements in under 3 minutes:

1. **Register a Player**:
   - Open [http://127.0.0.1:8000/register](http://127.0.0.1:8000/register).
   - Register user `playerone` with password `Password1$`.
2. **Log In**:
   - Log in at [http://127.0.0.1:8000/login](http://127.0.0.1:8000/login) with `playerone` / `Password1$`.
3. **Play a Game**:
   - Navigate to [http://127.0.0.1:8000/game](http://127.0.0.1:8000/game) and click **Start Game**.
   - Type a 5-letter word on your physical keyboard (e.g. `CRANE`) and press `Enter`.
   - Verify 3D sequential tile flip and colored evaluations (Green / Amber / Slate).
   - Complete the game (Win or Lose) and confirm the secret word is revealed.
4. **Verify Daily Limit**:
   - Play 2 more games to reach the 3-games/day limit.
   - Attempt to start a 4th game; verify the daily limit reached message and disabled start button.
5. **Create an Admin**:
   - In your terminal, run:
     ```powershell
     python -m app.create_admin
     ```
   - Enter username `adminuser` and password `AdminPass1*`.Example only — create your own credentials when prompted.
6. **Verify Admin Reports & Access Control**:
   - Log out of `playerone` and log in as `adminuser`.
   - Open [http://127.0.0.1:8000/admin/reports](http://127.0.0.1:8000/admin/reports).
   - Verify the **Daily Report** shows today's active user and games won.
   - Verify the **Per-User Report** for `playerone` shows words tried (3) and correct guesses.
   - In a private window logged in as `playerone`, attempt to visit `/admin/reports` $\rightarrow$ verify `403 Forbidden`.

---

## Testing

Run the automated test suite with pytest:

```powershell
python -m pytest -q
```

**Results**: **207 passed** across 7 test suites (`test_foundation.py`, `test_models.py`, `test_auth.py`, `test_admin_provisioning.py`, `test_daily_limit.py`, `test_game.py`, `test_reports.py`). All tests run against an isolated in-memory SQLite database.

---

## API Overview

| Method | Path | Auth / Role | Description |
|---|---|---|---|
| `POST` | `/register` | Public | Register new player account |
| `POST` | `/login` | Public | Authenticate user & issue signed session cookie |
| `POST` | `/logout` | Authenticated | Invalidate session cookie |
| `GET` | `/game` | Authenticated | Game page (READY state or active game) |
| `POST` | `/game/start` | Authenticated | Start new game (enforces 3 games/day limit) |
| `GET` | `/game/{game_id}` | Authenticated (Owner) | Get game state (target word hidden if active) |
| `POST` | `/game/{game_id}/guess` | Authenticated (Owner) | Submit 5-letter guess & receive evaluation |
| `GET` | `/admin/reports` | Admin Only | Admin reporting dashboard HTML |
| `GET` | `/admin/reports/daily` | Admin Only | Daily aggregate JSON report |
| `GET` | `/admin/reports/user/{user_id}` | Admin Only | Per-user activity JSON report |
| `GET` | `/admin/reports/users` | Admin Only | List registered users for admin dropdown |

---

## Troubleshooting

- **Port 8000 already in use**:
  Run on an alternate port: `$env:PORT="8080"; python run.py` (or check active processes via `Get-NetTCPConnection -LocalPort 8000`).
- **PowerShell script execution disabled**:
  Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` before activating `.venv`.
- **Browser showing old styles**:
  Perform a hard refresh (`Ctrl + Shift + R` or `Cmd + Shift + R`) to clear cached static assets.
- **Database not found or missing tables**:
  Ensure you ran `alembic upgrade head` followed by `python -m app.services.word_seed`.
- **Cannot log in as Admin**:
  Public registration creates Players only. Use `python -m app.create_admin` in the terminal to provision an Admin account.

---

## Project Status

**Completed & Fully Verified**. All OpenText functional, security, architectural, and reporting requirements are implemented and verified with 207 automated tests.
