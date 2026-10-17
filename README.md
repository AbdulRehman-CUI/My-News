# MyNews

MyNews is a local, privacy-conscious personal morning newspaper. It collects
real news from configured RSS/Atom feeds and optional TheNewsAPI access, prepares
usable article content locally, learns each reader's interests from explicit
choices and reading feedback, and creates a dated daily edition.

Readers can:

- Create and switch between local reader profiles.
- Choose broad interests, subtopics, regions, and a preferred local ready time.
- Browse adaptive recommendations in Discover.
- Read a stable, reader-specific Today's Paper.
- Save stories, provide feedback, and track reading progress.
- Search the personal library and resume previous editions.
- Download an edition as a traditional newspaper PDF.
- Run a separate local worker that prepares content and generates due editions.

All application data is stored locally in SQLite. The application does not
require an account service, cloud database, frontend build system, or deployment
platform.

## Architecture

The application is a small Flask and SQLite system with separate modules:

- `app.py` — Flask routes, sessions, onboarding, reader selection, web pages,
  feedback, saving, progress, library, and PDF download.
- `storage.py` — SQLite connection handling, foreign keys, and non-destructive
  schema migrations.
- `news.py` — RSS/Atom and optional TheNewsAPI ingestion, canonical URL
  deduplication, bounded article extraction, deterministic briefs/details,
  content-depth classification, and local embedding preparation.
- `recommender.py` — reader-scoped preferences, semantic anchors, recent-interest
  decay, exclusions, persisted LinUCB state, recommendation explanations, and
  feedback events.
- `editions.py` — dated edition creation, transactional reader/date uniqueness,
  immutable story snapshots, saved stories, and reading progress.
- `pdf_export.py` — Playwright Chromium PDF generation from immutable edition
  snapshots with local cache files.
- `worker.py` — separate local scheduling process that reuses ingestion and
  edition-generation services.
- `demo.py` — creates labeled local demo readers without creating fictional
  production stories.
- `templates/` and `static/` — responsive web templates, newspaper print
  template, and local styling.

### Data flow

1. `news.py` fetches shared provider content and stores normalized articles in
   SQLite. It is run manually or by the worker; page loads do not make separate
   provider requests for each reader.
2. Onboarding stores validated reader preferences and a saved IANA timezone.
3. `recommender.py` selects eligible stories using explicit interests, learned
   signals, semantic similarity, freshness, significance, diversity, and bounded
   exploration.
4. `editions.py` copies the selected fields into immutable edition-item rows.
   Later article updates, preference changes, and feedback do not rewrite a
   published edition.
5. The website reads those snapshots for Today's Paper and the archive.
6. `pdf_export.py` renders the same snapshots into a downloadable newspaper PDF.
7. `worker.py` prepares shared content ahead of reader cutoff times and claims
   due reader/date jobs without overlapping duplicate generation.

## Requirements

- Windows, macOS, or Linux.
- Python 3.12 recommended.
- Internet access for dependency installation and optional live ingestion.
- Chromium installed through Playwright for PDF downloads.
- A writable local directory for SQLite, cached models, and generated PDFs.

The application and automated tests can run offline after dependencies and
optional local model/browser assets have been installed. RSS ingestion works
without a TheNewsAPI key.

## Installation on Windows

From PowerShell:

```powershell
Set-Location -LiteralPath "C:\Users\J A\Desktop\Nascon 26'"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m pip check
```

If the Windows Python launcher is unavailable, use a normal Python 3.12
installation and replace the `py -3.12` command with its executable path.
The repository's local `.venv` must be created before running the commands below.

## Running the application

Start the web application in one PowerShell window:

```powershell
Set-Location -LiteralPath "C:\Users\J A\Desktop\Nascon 26'"
.\.venv\Scripts\python.exe app.py
```

Open <http://127.0.0.1:5000>. The server binds only to localhost and initializes
the SQLite database automatically.

Start the local worker in a second PowerShell window:

```powershell
Set-Location -LiteralPath "C:\Users\J A\Desktop\Nascon 26'"
.\.venv\Scripts\python.exe worker.py
```

Run one scheduling pass and exit:

```powershell
.\.venv\Scripts\python.exe worker.py --once
```

The computer and worker must be running for scheduled generation. If the
computer is off, no edition can be generated. On restart, the worker catches up
only the current local date when it is due; it does not fabricate missed
historical editions.

Stop each process with `Ctrl+C`.

## News ingestion

The manual ingestion command prepares the shared article pool:

```powershell
Set-Location -LiteralPath "C:\Users\J A\Desktop\Nascon 26'"
.\.venv\Scripts\python.exe news.py
```

To enable TheNewsAPI for that PowerShell session:

```powershell
$env:THENEWSAPI_KEY = "YOUR_REAL_SERVER_SIDE_KEY"
.\.venv\Scripts\python.exe news.py
```

Do not use the literal string `YOUR_REAL_SERVER_SIDE_KEY`. The key is read only
from the server-side environment and is never sent to browser JavaScript or
printed in request URLs. The repository does not automatically load `.env`;
`.env.example` contains placeholders only. Never commit a real key.

The command reports attempted and successful sources, new and duplicate
articles, usable and preview-only content, embedding reuse/creation, remaining
local API allowance, and redacted provider errors.

RSS/Atom feeds are configured in `news.py`. To replace the defaults, set
`MYNEWS_RSS_FEEDS` to a JSON object mapping feed URLs to supported topics:

```powershell
$env:MYNEWS_RSS_FEEDS = '{"https://example.com/feed.xml":["Technology"]}'
```

The ingestion path uses bounded timeouts and retries, canonical URL
deduplication, a persisted API request budget, safe public URL validation,
bounded extraction from configured publisher hosts, and explicit content-depth
labels:

- `full_text` — substantial extracted article text.
- `feed_text` — usable text supplied by a feed or API response.
- `preview_only` — insufficient content for a full reading edition.

Preview-only records are not silently treated as full articles.

## Local embeddings

The configured model is:

```text
sentence-transformers/all-MiniLM-L6-v2
```

It runs locally on CPU. Embeddings are cached by model identifier and article
content hash. The model input consists of the title, deterministic brief, and up
to 6,000 characters of deterministic detail. If the model cannot be downloaded,
ingestion reports the failure and remains usable for RSS/content checks; it does
not claim neural inference succeeded.

## Scheduling and timezones

Each completed reader profile stores an IANA timezone and local ready time.
`worker.py`:

- Prepares shared content up to six hours before due editions.
- Performs a bounded refresh within 30 minutes of the scheduled cutoff.
- Computes each reader's current local date and due time.
- Claims one reader/date job transactionally.
- Stores claim status, attempt count, timestamps, and recoverable errors.
- Limits retry attempts to three.
- Preserves successful editions and never overwrites them with a failed run.

Timestamps are stored in UTC while edition dates and schedules are reader-local.
For daylight-saving transitions, ambiguous times use the first occurrence.
Nonexistent spring-forward times use the first valid instant after the requested
wall-clock time.

The web edition displays its actual generation and cutoff timestamps. A worker
job is not a guarantee that a provider will return enough usable content; empty
and shorter editions are reported honestly.

## Demo readers

Create or reuse isolated, labeled local demo readers:

```powershell
Set-Location -LiteralPath "C:\Users\J A\Desktop\Nascon 26'"
.\.venv\Scripts\python.exe demo.py
```

Demo readers use the existing cached real-news pool. The command does not create
fictional production articles. Fictional stories are restricted to automated
test fixtures.

## Security and privacy

- SQLite is stored at ignored `instance/mynews.sqlite3`.
- The session secret is stored at ignored `instance/secret.key` unless
  `MYNEWS_SECRET_KEY` is supplied.
- Session cookies are signed, HttpOnly, and SameSite=Lax.
- POST actions require CSRF validation.
- SQL writes use parameters and foreign keys.
- Templates escape rendered values.
- Article extraction blocks private, loopback, link-local, and reserved
  destinations.
- API credentials remain server-side.

This is a local prototype, not a production authentication system. Anyone who
can use the computer can select any local reader profile. Public hosting would
require HTTPS, real authentication, authorization, and a separate deployment
design.

## PDF export

PDFs are generated from saved edition snapshots:

```text
GET /editions/<edition_id>/pdf
```

The export preserves story order, briefs, details, takeaways, dates, publishers,
and original source references. It does not rerank stories, regenerate text,
read mutable article content, or depend on remote images. Cached files are stored
under ignored `generated/`.

If PDF export reports that Chromium is unavailable:

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

## Tests and CI

Run the complete local suite:

```powershell
Set-Location -LiteralPath "C:\Users\J A\Desktop\Nascon 26'"
New-Item -ItemType Directory -Force .tmp | Out-Null
$env:TEMP = Join-Path (Get-Location) '.tmp'
$env:TMP = $env:TEMP
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

The tests use temporary SQLite databases and mocked providers. They cover
onboarding persistence, migration safety, RSS/API ingestion behavior,
recommendation learning and isolation, edition snapshots, saving, reading
progress, PDF signatures, archive search, ownership, scheduling, timezone
boundaries, DST resolution, duplicate claims, and bounded worker failures.

Offline GitHub Actions checks are defined in
[.github/workflows/ci.yml](.github/workflows/ci.yml). CI does not require live
news, TheNewsAPI credentials, a large embedding download, or Chromium.

## Known limitations

- Automatic worker execution requires the local computer and worker process to
  remain running.
- PDF bytes and route behavior are tested automatically; every PDF page still
  requires manual visual inspection for final typography and layout review.
- Real provider availability, content depth, and article quality vary by source.
- The local prototype has no public hosting, account authentication, or
  multi-device synchronization.
- No automatic scheduling service, deployment automation, or cloud persistence
  is included.

Review ignored files, credentials, generated PDFs, model caches, and database
files before staging. Do not commit secrets or runtime artifacts.
