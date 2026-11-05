# Production ingestion and recovery runbook

## Root cause and pipeline trace

This is a code diagnosis. It does not assert that the production database is
empty; the authenticated counters below establish its actual contents.

1. `api/index.py` imports the Flask factory. Neither that import nor a page load
   ran `news.ingest()`. `worker.py` is a local CLI loop under `__main__`, so Vercel
   never starts it as a daemon. Previously there was no HTTP ingestion route or
   scheduler configuration.
2. `news.py` fetches RSS or optional TheNewsAPI results, prepares extractive
   summaries, classifies content, and upserts articles by canonical URL. RSS
   works without a key or model. Feed summaries of at least 40 cleaned characters
   already qualify as `feed_text`; full-page extraction was not required for
   these articles. Shorter previews remain `preview_only`. Publisher allowlists
   can prevent extraction, including where feed and publisher hostnames differ.
   Ingestion now keeps sufficient feed text directly and avoids downgrading a
   previously usable article when later extraction fails.
3. `recommender.py` reads persisted non-preview articles. An empty table produces
   zero recommendations. Missing embeddings produce a zero semantic-match
   feature, not exclusion from ranking. Existing NumPy LinUCB, explicit choices,
   learned topics, freshness, significance, diversity, and adjacent exploration
   continue to operate. No synthetic vectors, model resets, or reseeding occur.
4. `editions.generate_edition()` previously persisted `status='empty'` and
   returned any reader/date edition forever. The paper route also skipped
   generation when that row existed. Empty rows now remain retryable; recovery
   fills the same edition ID. Any edition containing stories stays immutable,
   including its timestamps, article snapshots, saved stories, and progress.
5. PostgreSQL previously opened implicit transactions on SELECT, while helpers
   committed inside larger operations. `BEGIN IMMEDIATE` merely became `BEGIN`
   and provided no reader lock. The fix uses autocommit for standalone reads,
   explicit transactions for writes, and reader row locks through recommendation
   generation and snapshot publication. Nested helpers join the transaction.
   The reader/date unique constraint remains the final database invariant.
6. `INSERT OR REPLACE` in saved stories was SQLite-only; saving now uses a
   portable upsert and validates edition/story ownership. Progress now validates
   the item belongs to the supplied owned edition. Archive date searches cast
   PostgreSQL DATE to text.
7. `templates/shell.html` receives only a safe empty-state explanation: no news
   yet, only previews, or no stories matching preferences/exclusions. Provider
   failures, counters, and administration details stay behind bearer auth.

## Scheduler and deployment configuration

Keep the connected project's **Flask** framework preset and repository root.
`pyproject.toml` selects the existing `api.index:app` export; `vercel.json` keys
its function settings by `api/index.py`. Flask routes all paths, including the
cron path, through that application. No legacy builder or catch-all rewrite is
needed. `.python-version` selects 3.12. Production still installs
`requirements.txt`; `requirements-local.txt` is optional for local ML/PDF use.
Development models, databases, caches, and virtual environments are excluded
from deployment uploads and the function bundle.

The committed cron calls `GET /api/cron/ingest` daily at `01:00 UTC` (06:00 in
Asia/Karachi). Daily scheduling fits the Hobby plan; the exact connected plan
was not exposed by the available project metadata. Hobby allows a daily job
within the scheduled hour, so this may run between 06:00 and 06:59 Karachi time.
See [Vercel cron limits](https://vercel.com/docs/cron-jobs/usage-and-pricing) and
[Flask deployment configuration](https://vercel.com/docs/frameworks/backend/flask).

The existing production `CRON_SECRET` must be available to the deployment.
Vercel supplies `Authorization: Bearer <CRON_SECRET>` to cron requests. Both admin
routes deny access if the secret is unset, empty, or incorrect. Reader sessions
do not authorize administration. HEAD does not trigger ingestion. Responses are
JSON with `Cache-Control: no-store`. Provider errors contain a source index or
endpoint name and error class, never credential-bearing URLs or exception text.

No deployment, secret changes, database replacement, or paid integration is
performed by running the local tests. Deploy the reviewed code through the
existing Vercel project before using the new production endpoints. Confirm the
cron appears enabled in the deployed project's Cron Jobs settings. A config
file alone cannot prove that the control-plane job is enabled or has run.

### Optional free hourly refresh

`.github/workflows/ingest.yml` is an opt-in alternative. On this public repository,
standard Ubuntu GitHub Actions runners are free under
[GitHub's public repository billing rules](https://docs.github.com/en/billing/concepts/product-billing/github-actions).
To enable it, an authorized repository administrator must:

1. Store the **same existing** Vercel `CRON_SECRET` as the repository's Actions
   secret `CRON_SECRET`. Do not create a different endpoint secret or commit it.
2. Set the Actions repository variable `MYNEWS_EXTERNAL_INGEST` to `true`.
3. Ensure the workflow is on the default branch and enabled. It runs at minute
   17 each hour and also supports manual workflow dispatch.

The workflow is disabled by its job condition until explicitly configured and
is restricted to the original repository, preventing accidental fork calls.
The daily Vercel job may remain as a fallback: duplicate executions are safe.
GitHub schedules can be delayed or dropped and public scheduled workflows can
be disabled after 60 days of repository inactivity; see
[GitHub schedule behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
The workflow does not check out source, install packages, or access the database.
It only calls the deployed authenticated endpoint. Vercel/provider usage limits
still apply. Without a provider key this can run RSS-only indefinitely.

## Exact first production ingestion

Run only after the reviewed code is deployed. Obtain the existing `CRON_SECRET`
through your normal secret manager into this PowerShell process environment;
do not paste its value into committed scripts, URLs, logs, or chat.

```powershell
if (-not $env:CRON_SECRET) { throw 'Load the existing production CRON_SECRET first.' }
$base = 'https://mynews-drab-eight.vercel.app'
$headers = @{ Authorization = "Bearer $env:CRON_SECRET" }

# Inspect actual database state first.
Invoke-RestMethod -Uri "$base/api/admin/ingestion" -Headers $headers -Method Get

# One authorized, bounded initial refresh. Repeating this call is safe.
Invoke-RestMethod -Uri "$base/api/cron/ingest" -Headers $headers -Method Get -TimeoutSec 65

# Confirm durable counters and completion status.
Invoke-RestMethod -Uri "$base/api/admin/ingestion" -Headers $headers -Method Get
```

Expected fields from ingestion: `attempted_sources`, `successful_sources`,
`new_articles`, `duplicates`, `usable_articles`, `preview_only_articles`,
`total_eligible`, `last_success_at`, redacted `errors`, `provider_requests`,
`processed`, `bounded`, and `status`. The shorter original counter names also
remain for local CLI compatibility. Usable/preview counters count processed
records, including duplicates; `new_articles` counts newly inserted records.

`busy` (HTTP 200) means another run holds the lease; inspect diagnostics after
it completes. `partial` means at least one source parsed successfully but some
providers or records failed. `failed` returns HTTP 503 and retains the prior
successful timestamp. A successful source can contain zero eligible stories:
always check `total_eligible`. Do not mark deployment verified solely from HTTP
200 or a successful-source counter.

For API failures or quota exhaustion, omit the optional `THENEWSAPI_KEY` in a
local isolated test to verify RSS separately. Production configuration changes
remain an administrator action. The hourly API budget is persisted and locked;
RSS does not consume it. No API key is necessary for the default feeds.

## Diagnostics and operational verification

`GET /api/admin/ingestion` with the same bearer header reports:

- Database connectivity, article count, eligible count, latest article storage
  timestamp, last ingestion start/completion, status, last success, and report.
- `scheduled_ingestion_configured`: the deployed production environment contains
  the committed cron definition and a configured bearer secret. This does not
  verify the platform scheduler is enabled; `scheduler_execution_verified`
  deliberately remains false. Check control-plane logs and advancing timestamps.
- `embedding_model_available: false` and `embedding_mode: topic_features`: this
  HTTP ingestion path deliberately uses `model=None` and does not download an
  ML model. Stored embeddings are still used by ranking when present.

If the database becomes unavailable, the initialized app returns a redacted
503 diagnostic response. A cold-start database failure can prevent Flask from
initializing at all; then inspect Vercel startup logs without printing the
connection string. No endpoint can diagnose a process that failed to start.
`interrupted` means a run's lease expired while its persisted status was still
running, such as a platform termination. The next authorized run can reclaim it.

To verify Discover and Today's Paper manually after the CLI checks:

1. Confirm `eligible_article_count > 0` and `last_success_at` advances. If there
   are only previews, inspect the redacted report and the configured feed quality.
2. In your own existing reader session, visit Discover. RSS headlines should
   appear if they match selected or adjacent topics and are not excluded.
   If none match, review My Editor. General interests allow a balanced pool.
3. Complete onboarding if needed, then revisit Today's Paper. A previously empty
   edition for the current **reader-local date** fills automatically. Refresh
   again: the populated edition's ID, order, and snapshots must stay stable.
4. Save a story and mark it read. Refresh and confirm both persist. A different
   reader must not see your edition, saved stories, or reading progress.
5. Confirm scheduled invocations appear in platform logs and advance the stored
   ingestion timestamps on the next due run. Daily/hourly ingestion is separate
   from reader edition generation; no worker loop is assumed on Vercel.

No browser or browser automation was used to develop or test these changes.
The steps above are a user verification procedure after deployment.

## Bounds, transactions, and recovery

- A refresh has a 35-second cooperative processing budget, at most four RSS
  feeds plus two API sources, six records per source by default (hard cap ten),
  and at most 40 processed articles. All entries and payload bytes are bounded.
- At most 16 outbound requests total, two attempts per fetch, three redirects,
  four publisher extraction attempts, a four-second request timeout shortened
  to remaining budget, and 2 MB per response. API redirects are rejected so
  credentials are never forwarded. RSS/extraction redirects are revalidated.
  Timing is checked between requests, streamed chunks, and articles. DNS and
  third-party parser execution are cooperative; the Vercel function's 60-second
  hard limit remains the outer bound. A killed invocation is recoverable.
- A durable 120-second database lease excludes overlapping ingestion across
  serverless instances and CLI workers. Each article transaction checks lease
  ownership before its upsert. A stale worker cannot overwrite the new owner's
  diagnostics. Successful articles commit individually, so partial failures do
  not discard earlier sources, and network I/O holds no database write lock.
- PostgreSQL uses transaction-scoped schema locking and reader row locks,
  compatible with Neon pooled connections. Explicit write transactions have
  five-second statement timeouts. SQLite uses `BEGIN IMMEDIATE`. Recommendation
  state and edition snapshots commit together; a failed snapshot rolls back its
  learning/recommendation writes. The database enforces reader/date uniqueness.
- Empty editions are retryable placeholders, never worker successes. Recovery
  preserves their ID and reader/date. Non-empty editions are not rewritten.
  Worker claims use an atomic affected-row check; active claims cannot be stolen
  just because they are not yet successful. Failed local jobs have bounded retries.
- SQLite migration 7 and the PostgreSQL schema add only ingestion state. Existing
  article identities, vectors, preferences, learning, editions, and reader IDs
  remain in place. No automatic database clearing or demo reseeding exists.

## Tests and remaining limits

```powershell
New-Item -ItemType Directory -Force .tmp | Out-Null
$env:TEMP = Join-Path (Get-Location) '.tmp'
$env:TMP = $env:TEMP
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

Providers and optional PDF rendering are mocked. Concurrency tests use separate
database connections and synchronization barriers. PostgreSQL integration tests
require a separate disposable `MYNEWS_TEST_DATABASE_URL`; do not set it to a
production database. They create and remove only their own temporary schema.

Production dependencies remain unchanged and exclude optional ML/PDF packages.
Measure the built Linux function artifact before promotion; the platform's
standard Python limit is 500 MB uncompressed
([Python runtime documentation](https://vercel.com/docs/functions/runtimes/python)).
A local Windows installation size is a useful check but not the deployed bundle.

Verification on 2026-10-22:

- 56 tests discovered: 54 passed and the two live PostgreSQL tests skipped because
  no disposable `MYNEWS_TEST_DATABASE_URL` was available. SQLite concurrency and
  offline PostgreSQL transaction/normalization contracts passed.
- `pip check` passed using the unchanged production requirements in Python 3.12.
- The actual `api.index:app` export imported with no SentenceTransformer, PyTorch,
  or Playwright installed. Both unauthenticated admin routes returned 401;
  `/profiles`, `/static/style.css`, and `/static/screen.js` returned 200 locally.
- Resolved CPython 3.12 Linux x86_64 dependency wheel payload: **119.40 MiB**,
  33 packages. Downloaded Linux wheels were checked against PyPI SHA256 hashes;
  `sgmllib3k` used its locally built universal wheel. The Windows installation,
  including pip and bytecode, measured 128.48 MiB. These are dependency checks;
  Vercel's complete built function, live Neon behavior, provider reachability,
  and actual scheduled invocation remain post-deployment verification steps.

Neural model creation and PDF generation remain local optional features.
`requirements-local.txt` and a local Chromium installation restore them locally.
Without Playwright, PDF download returns a clear 503 rather than crashing import.
Any runtime PDF cache uses temporary storage on Vercel and is not durable.
RSS descriptions can produce short editions; no full-text or provider-availability
guarantee is made. A ready-time guarantee across all reader timezones still
requires a separate edition scheduler; the news cron only refreshes content.
Reader ownership remains based on signed sessions, without multi-device accounts.
