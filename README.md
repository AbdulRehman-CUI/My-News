# MyNews — Phase 1

A local Flask application for persistent reader profiles and choice-based onboarding. Read [MYNEWS_PROJECT_REFERENCE.md](MYNEWS_PROJECT_REFERENCE.md) for the complete product plan. Only Phase 1 is implemented.

## Run the application

The project already has a local `.venv`. From Windows PowerShell:

```powershell
Set-Location -LiteralPath "C:\Users\J A\Desktop\Nascon 26'"
.\.venv\Scripts\python.exe app.py
```

Open **http://127.0.0.1:5000**. Stop with Ctrl+C. Startup initializes the database automatically; no API key, model, browser download, or frontend build is needed. Debug mode is off and the server binds only to `127.0.0.1`.

## Set up from scratch

Use Python 3.12 (verified here with 3.12.14), including pip and venv. On a machine with the standard Windows Python launcher:

```powershell
Set-Location -LiteralPath "C:\Users\J A\Desktop\Nascon 26'"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe app.py
```

On this computer `py` is absent and `python` points to an unusable Windows Store alias. The Codex bundled Python was verified instead. These are the exact alternative setup commands; activation and execution-policy changes are unnecessary:

```powershell
Set-Location -LiteralPath "C:\Users\J A\Desktop\Nascon 26'"
$mynewsPython = 'C:\Users\J A\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
New-Item -ItemType Directory -Force .tmp | Out-Null
$env:TEMP = Join-Path (Get-Location) '.tmp'
$env:TMP = $env:TEMP
& $mynewsPython -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe app.py
```

The temporary-directory override works around a sandbox temp-directory permission error encountered during setup. It applies only to that PowerShell session. The bundled runtime path is machine-specific; use a normal Python 3.12 installation on other machines. Installation needs network access to PyPI. App operation and tests are offline after installation.

## What works

- Create profiles with an optional display name or generated `Reader N` name; select profiles and resume setup.
- Eight stages: optional age, education, multiple activities, multiple broad interests, adaptive subtopics, regions, labeled fictional headline calibration, and confirmed timezone/native time selection.
- All twelve broad interests have subtopics in `taxonomy.py`. No free-text interest questions, reading-duration setting, or demographic inference.
- Back, Next, and Skip save selections. JavaScript also saves draft changes, including valid morning settings. Wait for the saved message before refreshing; without JavaScript use Back/Next to persist changes.
- Skipping broad interests records an explicit general-interest state; skipping regions records Worldwide. Worldwide must be selected alone or replaced with specific regions.
- Browser timezone is a suggestion only. Confirmation is always required to finish, including after resuming a draft. An IANA identifier and strict `HH:MM` local time are validated server-side.
- Today's Paper, Discover, My Library, and My Editor load with honest Phase 1 states. My Editor summarizes explicit preferences and links back to the working setup flow. Editing a setup choice marks setup incomplete until morning confirmation is completed again.

## Persistence and local identity

SQLite is stored at ignored `instance/mynews.sqlite3`. The schema has only `readers` and `preferences`: reader creation time, completion/current/furthest stage, and a validated JSON preference document. `PRAGMA user_version = 1` initializes the schema; a newer database version fails explicitly. Foreign keys, checks, parameterized queries, and transactions protect writes. Onboarding writes take an immediate transaction before reading and updating preferences.

Preferences include `age`, `education`, `activities`, `interests`, `general_interest`, `subtopics` (`Topic:Subtopic` values), `regions`, `calibration` (setup IDs), `calibration_preferences` (topic/subtopic snapshots), `timezone`, `morning_time`, and `schedule_confirmed`. Missing optional draft fields mean the stage has not yet been saved. Skips save explicit empty/default values.

The selected reader ID and CSRF token live in a signed HttpOnly/SameSite=Lax session cookie. The signature key is generated once into ignored `instance/secret.key`, so sessions survive app restarts. An optional `MYNEWS_SECRET_KEY` environment variable overrides that file. `.env.example` is documentation with placeholders; `.env` is **not** automatically loaded. Never commit an actual key. HTTP cookies are appropriate only for this localhost prototype; public hosting needs HTTPS with Secure cookies and real authentication/authorization.

All state changes use POST and CSRF validation. Onboarding resolves ownership from the session and rejects submitted reader/profile/user identifiers. The explicit local profile-selection endpoint intentionally accepts a profile ID. Anyone who can use the app on this computer can select any local profile: **this is not production authentication or a privacy boundary between local users**. No data is sent to news services or third-party assets. Templates escape names and values; restrictive content/security headers and host validation are enabled.

Restarting preserves profiles, incomplete choices, confirmed settings, and the selected session. If cookies are removed, select the saved profile again. Back up the database while the app is stopped if needed. Do not delete `instance/` to clear browser checks unless you intend to remove all local profiles and the session key.

## Checks

```powershell
Set-Location -LiteralPath "C:\Users\J A\Desktop\Nascon 26'"
New-Item -ItemType Directory -Force .tmp | Out-Null
$env:TEMP = Join-Path (Get-Location) '.tmp'
$env:TMP = $env:TEMP
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

Tests use temporary SQLite databases and test secrets, never the real application database or live news. See `BUILD_PROGRESS.md` for actual automated and browser outcomes. For a manual check, complete setup, refresh after saved drafts, go Back/Next, switch profiles, restart the app, and reopen My Editor. Repeat on a narrow viewport. Browser verification created local profiles named `Browser check` and `Reader 2`; they contain only setup choices, no fabricated news.

## Phase 2 news ingestion

Phase 2 adds a shared SQLite article cache, configurable RSS/Atom ingestion, optional
TheNewsAPI `/v1/news/top` and `/v1/news/all` ingestion, canonical URL deduplication,
content-depth classification, deterministic extractive text preparation, and optional
local MiniLM embeddings. RSS works without an API key. The API key is read only from
the server-side `THENEWSAPI_KEY` environment variable; `.env` is documentation only
and is not loaded automatically.

Fetch and prepare the pool manually:

```powershell
Set-Location -LiteralPath "C:\Users\J A\Desktop\Nascon 26'"
.\.venv\Scripts\python.exe news.py
```

The command reports provider successes/errors, new and duplicate records, usable versus
preview-only content, embedding reuse/creation, and the remaining local API allowance.
The default feeds are in `news.py`; set `MYNEWS_RSS_FEEDS` to a JSON object to replace
them. Article extraction is bounded to configured feed hosts, refuses private/local
destinations, and does not bypass access controls. `full_text` needs substantial source
text, `feed_text` uses a sufficiently detailed feed/API body, and `preview_only` is
not sufficient for a future full newspaper edition.

The embedding input is the title, deterministic brief, and up to 6,000 characters of
deterministic detail. Sentence Transformers runs on CPU and caches vectors with the
article content hash and `all-MiniLM-L6-v2` model identifier. If the model cannot be
downloaded, ingestion remains usable for RSS/content checks but reports that neural
embeddings are unavailable; this is not embedding acceptance.

## Phase boundary and next integrations

Phase 2 does not run LinUCB or behavioral learning, generate editions, export PDFs, or schedule work. It has article cache and embedding tables, but no edition/event/recommendation behavior.

Phase 2 can reuse the taxonomy, profile preference document, database version mechanism, and `calibration_candidates()` function. Replace the separately stored `setup_examples.json` candidates with cached real articles and migrate calibration references deliberately; never ingest fictional examples into a live news table. Optional age/education must not seed interests or expertise.

Upcoming installation requirements, **not installed or required by this phase**:

- Phase 2: verify/pin feedparser, requests, trafilatura, Sentence Transformers and its CPU runtime; download `sentence-transformers/all-MiniLM-L6-v2` once. Internet, model cache space, and sufficient RAM/CPU will be needed. Model inference/download compatibility has not been checked here. No custom neural training or paid API is required. Recheck optional TheNewsAPI limits/docs before integration; RSS must work without a key.
- Phase 5: verify/pin Playwright, then run `.\.venv\Scripts\python.exe -m playwright install chromium` after installing that future dependency. Chromium is a separate download; PDFs will need local browser execution and a writable generated-files directory. This installation and PDF rendering have not been run here.
- Phase 6: scheduling needs the local machine/worker running. Phase 1 only saves the desired timezone/time; it promises no automatic delivery. `tzdata` is already installed for Windows IANA timezone support.

The local Git repository has been initialized for review; no commit, push, or GitHub remote was created. Review ignored/runtime files before adding files, configure your intended GitHub remote, and perform the requested commit/push yourself.
