# MyNews build progress

## Neon/Vercel deployment preparation — current

Implemented deployment-compatible storage and application wiring:

- `storage.py` now selects a psycopg PostgreSQL adapter when the server-side
  `DATABASE_URL` is set and retains the existing SQLite path otherwise.
- Neon initialization is repeatable and non-destructive, uses PostgreSQL JSONB,
  timestamps, conflict handling, foreign keys, indexes, and a migration ledger.
  The local SQLite file is never opened or modified in PostgreSQL mode.
- Cross-database writes now use portable timestamps/conflict syntax, explicit
  article columns, PostgreSQL `RETURNING id` where needed, and a normalized
  dictionary-row adapter for JSON/date values.
- `api/index.py` is a Vercel Flask entrypoint. Production requires
  `MYNEWS_SECRET_KEY`, enables secure cookies, and applies trusted-host
  configuration from `MYNEWS_ALLOWED_HOSTS`/`VERCEL_URL`.
- Public deployments do not expose the local profile chooser or permit
  unrestricted numeric profile selection. A newly created reader is bound to
  its signed session. Full multi-device account authentication and importing
  existing local profiles remain deployment gaps.
- `.env.example` and `README.md` document Neon/Vercel variables, local-data
  separation, ephemeral PDF/model storage, and the limitation that a persistent
  local worker cannot run inside a standard Vercel function.
- `tests/test_postgres.py` provides an optional Neon round-trip check and skips
  without `DATABASE_URL`.

Verification for this change:

- `python -m unittest discover -s tests -v`: 30 passed, 1 skipped (PostgreSQL
  integration skipped because no deployment connection string is configured).
- Python compilation passed.
- `pip check` passed.
- `from api.index import app` passed with the local SQLite fallback.
- No Neon/Vercel deployment credential was available, so live PostgreSQL schema,
  serverless PDF/model packaging, Vercel routing, and deployed cookie/host
  behavior were not run.
- No browser, visual, live provider, or deployment checks were performed for
  this deployment task.

## Phase 1 — completed, 17 October 2026

Implemented only the application foundation, persistent local reader profiles, and choice-based onboarding. The complete `MYNEWS_PROJECT_REFERENCE.md` was read before editing and preserved. No existing application or Git history was present; no `AGENTS.md` was found in the workspace or checked ancestor locations. A local Git repository was initialized on `main` for review; no files were staged and no commit, push, or GitHub remote was created.

### Completed behavior

- Flask/Jinja application with system fonts, local static CSS, and a small vanilla JavaScript enhancement. No frontend build framework, external assets, Docker, or service layer.
- Responsive navigation for Today's Paper, Discover, My Library, and My Editor. Today's Paper and My Library remain honest pre-edition states; Discover and My Editor now use the Phase 3 learning loop without invented articles or statistics.
- Optional/generated local profile names, selection through CSRF-protected POST, session-selected ownership, persistent profiles/completion/resume stage, separate preferences for each reader.
- Eight onboarding stages with optional skips, visible progress, Back/Next, and clear single/multiple choice labels. Every one of the twelve categories has adaptive subtopics, maintained in `taxonomy.py`.
- Regions include Worldwide and selectable countries/regions. Worldwide is exclusive; skipped/empty regions default to Worldwide.
- Clearly fictional calibration examples are isolated in `setup_examples.json`, shown only during setup, and saved as explicit topic/subtopic preferences. `calibration_candidates()` is the replacement point for Phase 2 real cached articles.
- Browser timezone suggestion, an IANA timezone selector, native time input, server-side validation, and required explicit final confirmation. Valid schedule drafts survive refresh without completing setup. Back remains available if unfinished schedule input is invalid.
- Optional age/education never infer interests or expertise. Skipped interests persist `general_interest: true`. Completion welcomes the reader and states that an edition has not been generated.
- Draft autosave on choice changes, ordered so a stale draft does not overwrite a later navigation submission. Back/Next/Skip also persist without JavaScript. Refresh after the saved status appears; a network request interrupted before it finishes is not a committed save.
- My Editor displays saved explicit choices and confirmed morning settings; setup can be reviewed through the existing wizard. Saving edits marks onboarding incomplete until the final confirmation is completed again.
- SQLite tables preserve `readers` and `preferences`, with Phase 2 article/cache tables and Phase 3 learning/recommendation/event tables added through non-destructive migrations. Foreign keys, checks, parameterized queries, transactions, and schema versioning remain enabled.
- Random persistent ignored session secret, optional environment override, HttpOnly/SameSite cookies, CSRF on every POST, host validation, Jinja escaping, restrictive CSP and related headers. Submitted reader identifiers are rejected on preference updates. Local profile selection is intentionally not authentication.
- `.gitignore`, placeholder-only `.env.example`, pinned installed dependencies, PowerShell setup/start/check instructions, future model/Chromium requirements, and the current limitations documented in `README.md`.

### Automated checks — passed

Command (run with a writable project-local TEMP/TMP in this sandbox):

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

Nine unittest checks pass against independent temporary SQLite databases:

1. Profile persistence, generated names, schema version, selection after app recreation.
2. Valid/invalid IANA timezones and strict `HH:MM` values, including boundary times.
3. Saved drafts, refresh markup, Back/Next preservation, and incomplete setup resume.
4. Two readers' independent activities/interests/context; attempted cross-profile updates using `reader_id`, `profile_id`, or `user_id` are rejected without changing either profile.
5. Full completion, topic/subtopic calibration snapshots, persisted schedule, and app recreation.
6. All optional skips, explicit general-interest and Worldwide defaults, invalid/unconfirmed schedules rejected.
7. Morning drafts persist but never complete setup; invalid unfinished schedule does not block Back.
8. Invalid categories/subtopics/calibration/region conflicts rejected; changing broad interests prunes stale dependent choices; all taxonomy/example mappings are valid.
9. CSRF failure handling (including non-ASCII tokens), no premature wizard jumps, escaped names, valid shell routes/security headers, hostile Host rejection, missing profiles, and overlong names.

`pip check`: no broken requirements. Verified runtime: Python 3.12.14. Installed/pinned: Flask 3.1.3, Werkzeug 3.1.9, Jinja2 3.1.6, MarkupSafe 3.0.4, itsdangerous 2.2.0, click 8.5.0, blinker 1.9.0, tzdata 2026.5.

`git check-ignore` confirms `.env`, `.venv`, database/session-secret files, `.tmp`, model paths, and generated PDF paths are excluded. `git status --short --untracked-files=all` shows source/documentation only. The pre-existing reference remains unmodified. No real secret is in source or `.env.example`.

### Browser checks — passed

Performed in the Codex in-app browser against a real server bound to `127.0.0.1:5000`:

- Complete setup for `Browser check`: age/education skipped; Studying + Freelancing; Technology + Sports; AI + Cricket; Pakistan; fictional Technology/AI calibration; confirmed Asia/Karachi / 08:15.
- Refresh before advancing from interests retained both checked values. Back from subtopics and Next retained AI + Cricket. Morning drafts survived refresh and required a fresh confirmation.
- A second profile was created without a name (`Reader 2`). Optional stages were skipped, including broad interests, subtopics, regions, and calibration; welcome acknowledged general interests and limited personalization. The profile chooser resumed its incomplete state before completion.
- All four navigation links work; Discover shows prepared recommendations, and My Editor shows the selected reader's learning state and controls. Library remains an honest pre-edition state.
- Stopped the Flask process, recreated/checked the local virtual environment, restarted the process, and refreshed the same browser session. The selected profile survived; both completed profiles remained selectable. Switching back to `Browser check` retained Technology/Sports and Asia/Karachi / 08:15.
- Visually inspected profile creation, choice wizard, subtopics, welcome, and editor. Explicit viewport checks at 1365×900 and 390×844; mobile navigation, wrapping, controls, and selected states are usable. DOM bounds showed no horizontal overflow. Temporary viewport override was reset.
- Saved screenshots in ignored `output/phase1-desktop.jpg` and `output/phase1-mobile.jpg`. Browser test profiles remain in the ignored runtime database; they contain no news data.

### Setup issues resolved

- The system `python` command is an unusable Store alias and `py` is missing. Used Codex's bundled Python to create the required local `.venv`; README includes both portable launcher commands and the exact working machine-specific alternative.
- The sandbox TEMP location rejected ensurepip writes. A project-local ignored `.tmp` override resolved it.
- Sandboxed pip DNS/network access failed. Installing Flask/tzdata with approved network access succeeded. Requirements were frozen from the installed environment and checked; no unrelated dependencies were installed.
- Browser access to the sandboxed server failed. The localhost-only server was run outside sandbox network isolation for browser checks; binding remained `127.0.0.1`.
- Early checks caught error-page context handling and Windows test database handles; both were corrected. Recreating a virtual environment while its Python executable was serving the app was rejected by Windows; stopping the app before recreation resolved it. All final automated checks pass.

### Not run / limitations

- Production authentication, public deployment, and HTTPS cookie behavior: not run; out of scope. Every local user who can reach this app may select any local profile. Profiles are not private accounts.
- No GitHub remote, commit, or push. The user must review and configure the intended repository before publishing.
- No physical-phone or assistive-technology session. Browser viewport inspection was performed; keyboard focus styles, form labels, live saved/error messages, and native controls are included.
- Embedding model download/inference, live news ingestion, Chromium installation/PDF rendering, learning, edition generation, and scheduling: not run and not implemented, by the Phase 1 boundary. Future dependency compatibility and performance remain to be checked in their phases.
- With JavaScript disabled, choices persist on form navigation rather than on change. `.env` files are not automatically loaded; README explains the environment variable or generated-secret options.

## Phase 2 — news acquisition and content understanding

Implemented:

- Non-destructive schema migration from version 1 to version 2. Existing readers and preferences remain intact.
- Shared SQLite article cache with canonical URL uniqueness, publication-date preservation (unknown remains `NULL`), normalized metadata, topic mapping, content hashes, story groups, and embedding fields.
- Configurable RSS/Atom feeds with an RSS-only path and optional TheNewsAPI `/v1/news/top` and `/v1/news/all` support.
- Finite HTTP timeout, one bounded retry, server-side API-key parameters, persisted hourly local API allowance, duplicate prevention, and redacted provider errors.
- Bounded configured-host extraction using Trafilatura, private/local destination rejection, deterministic briefs/details, and `full_text`/`feed_text`/`preview_only` labels.
- MiniLM embedding integration on CPU with content-hash/model reuse. The model is lazy-loaded by the ingestion command; failures are reported without pretending lexical content is neural.
- Calibration now prefers cached real stories and displays publisher/date metadata. Fictional examples remain a fallback when the cache is empty, and onboarding does not perform live requests.
- Manual command: `.\.venv\Scripts\python.exe news.py`.

Verification:

- `.\.venv\Scripts\python.exe -m unittest tests.test_foundation tests.test_news -q`: 14 tests passed.
- Mocked checks cover migration/profile preservation, RSS-only ingestion, deduplication, unknown dates, depth classification, embedding-cache reuse, unsafe extraction rejection, and real cached calibration rendering.
- Browser tools and visual checks were not used.

Not run:

- No live provider smoke check was performed because no API key was supplied and live crawling was not required for the focused offline verification.
- The embedding model was not downloaded during tests; the mocked cache test verifies reuse, while the CLI reports model-download failures explicitly.
- Phase 3 learning and recommendation ranking are implemented; editions, PDFs, and scheduling remain unimplemented.

### What Phase 2 can build on

Use the existing taxonomy, session-selected profile ownership, validated persistent preferences, transaction/schema-version mechanism, article cache, and embeddings. Phase 3 now consumes that prepared pool; Phase 4 should preserve recommendation evidence when creating immutable edition snapshots.

## Phase 3 — adaptive recommendations and feedback learning

Implemented:

- Version-3 migration adding `reader_learning`, `recommendations`, and `feedback_events`.
- Per-reader topic weights, decayed recent weights, positive semantic anchors, evidence counts, and explicit exclusions.
- Deterministic retrieval across direct interests and a bounded adjacent-topic map. Duplicate story groups and preview-only records are excluded.
- Persisted `linucb-v1` policy with positive identity regularization and an eight-value versioned feature vector: explicit match, learned topic, recent topic, semantic match, freshness, significance, diversity, and exploration.
- Recommendation-time feature snapshots, policy metadata, explanations, and visible-impression records.
- More/less, save/unsave, source-open, skip, and active-reading event support with unique event IDs, latest explicit-rating correction, one-time covariance updates, and reward-vector corrections.
- Functional Discover and My Editor routes with ownership checks, exclusions, learned evidence, reset, and setup/schedule editing.

Verification:

- `.\.venv\Scripts\python.exe -m unittest tests.test_foundation tests.test_news tests.test_recommender -q`: 18 tests passed.
- Fixtures cover cold start, score explanations, policy parameter changes, duplicate feedback, later reward correction, exclusions, reset, restart persistence, reader isolation, migration, and Discover rendering.
- No browser or visual checks were performed.

Known gaps:

- Phase 4 must snapshot recommendations into dated editions; Discover currently creates fresh recommendation records per request.
- Source-open and active-reading events are supported by the event endpoint but do not yet have reading-page instrumentation.
- The policy is deterministic and exposes no selection propensity. Recommendation quality is not measured; fixtures demonstrate mechanism only.

## Phase 4 — personalized daily web editions

Implemented:

- Version-4 non-destructive migration adds reader-scoped `editions`, immutable
  `edition_items`, `saved_stories`, and `reading_progress` tables. A unique
  `(reader_id, local_date)` constraint and transactional claim make generation
  idempotent; published snapshots do not change when source articles or preferences
  later change.
- `generate_edition()` is a callable manual/first-edition service. It reuses the
  Phase 3 recommendation pool and records cutoff/generation times, timezone, profile
  snapshot, policy version, sections, source metadata, deterministic briefs/details,
  selection reasons, takeaways, and actual word counts. Empty and short editions are
  represented honestly.
- Today's Paper renders relevant stories with topic sections, expandable details,
  source links/dates, text-only fallbacks, feedback, save/unsave, mark-seen
  impressions, and persistent reading progress. The main estimate uses 220 words per
  minute and the edition stores word counts; no padding or reading duration selector
  was added.
- Onboarding completion triggers first-edition generation when cached recommendations
  exist. Reopening today's paper does not regenerate or alter it. My Library lists
  owned editions and reader-scoped saved stories. Edition routes enforce ownership.

Verification:

- `.\.venv\Scripts\python.exe -m unittest discover -s tests -q`: 21 tests passed,
  including Phase 4 idempotency, immutable snapshots, personalization, save/progress,
  ownership, onboarding generation, and the Phase 1–3 regression suite.
- No browser, visual, screenshot, or browser automation checks were performed.

Known gaps:

- The paper currently exposes an explicit “Mark seen” action rather than automatic
  viewport instrumentation; no browser JavaScript was added under the requested
  validation constraints.
- Real-world editorial importance and recommendation quality are not claimed.
- PDF/print layout and automatic scheduling remain out of scope for Phase 4.

## Phase 5 — newspaper PDF export and archive

Implemented:

- Version-5 non-destructive migration adds immutable `image_url` snapshots to
  edition items. PDF export reads only the saved edition and item rows; it never
  reranks, regenerates summaries, or reads mutable article content.
- Added a separate traditional newspaper template with masthead, date, lead story,
  topic sections, readable detail columns, source references, and Playwright page
  numbers. Interactive controls are excluded from the PDF.
- Added `/editions/<edition_id>/pdf`, ownership checks, meaningful missing-browser
  errors, and ignored filesystem caching keyed by edition ID and generation revision.
  Remote images are not fetched during export, so PDF generation is not blocked by
  image hosts.
- My Library now supports title/summary search, dated previous editions, resume
  links, saved-story summaries, and old-edition PDF downloads. Existing saves and
  reading progress remain reader-scoped and visible.

Verification:

- Installed `playwright==1.51.0` and Chromium with
  `.\.venv\Scripts\python.exe -m playwright install chromium`.
- `.\.venv\Scripts\python.exe -m unittest tests.test_editions tests.test_foundation tests.test_news tests.test_recommender -q`: 22 tests passed.
- Tests verify PDF signature (`%PDF-`), `application/pdf` content type, archive search,
  PDF ownership isolation, Phase 4 snapshot behavior, save/progress persistence, and
  Phase 1–3 regressions.
- `pip check`, Python compilation, and `git diff --check` passed.

Known gaps:

- Automated checks verify PDF bytes and route behavior; visual inspection of every
  rendered PDF page was not performed in this terminal-only run.
- PDF output intentionally uses text-only source snapshots and does not claim that
  external publisher images remain available.
- Automatic scheduling remains out of scope for Phase 5.

## Phase 6 — scheduling and end-to-end verification

Implemented:

- Added standalone [worker.py](worker.py), reusing `news.ingest()` and
  `editions.generate_edition()`. It prepares shared content up to six hours ahead,
  requests a bounded near-cutoff refresh within 30 minutes, computes due readers
  using saved IANA timezone and morning-ready time, and generates only the current
  local date.
- Added version-6 `worker_jobs` persistence with atomic reader/date claims,
  statuses, attempt counts, timestamps, bounded three-attempt retries, and
  recoverable failure messages. Existing successful editions are never deleted or
  overwritten. Restart catch-up is limited to today's due edition.
- Documented DST policy: ambiguous local times use the first occurrence; nonexistent
  spring-forward times use the first valid instant after the requested wall time.
  Actual cutoff/generation timestamps remain visible in editions. The worker is a
  separate local process and cannot run while the computer is off.
- Added [demo.py](demo.py) for isolated labeled demo profiles. It creates no
  fictional stories and reuses real cached news when available.
- Added offline GitHub Actions checks in `.github/workflows/ci.yml`; CI runs the
  deterministic unittest suite and does not require live news, model downloads, or
  Chromium installation.

Verification:

- Worker tests use injected clocks and cover timezone/date boundaries, DST
  resolution, duplicate claims, bounded failure persistence, and reader isolation.
- Existing end-to-end tests cover two readers, fixture content, feedback/policy
  persistence, editions, PDF signature/content type, archive search, ownership,
  and restart-compatible migrations.
- Live-source ingestion previously produced cached real articles; Playwright
  Chromium was installed and PDF bytes were verified.

Not run:

- No long-running worker was left running.
- No browser visual inspection of every PDF page or mobile viewport was performed
  in this terminal-only validation run.
- No real model download or live API smoke request was repeated during Phase 6.

## Frontend redesign — vibrant editorial interface

Implemented the requested screen redesign using Flask/Jinja, system fonts, local
CSS, and a small image-failure script. No framework, icon package, CDN, external
design service, browser tool, renderer, screenshot, or subagent was used for this
work. Visual verification is explicitly **not performed**; the reader will check it
manually.

Changes:

- Replaced the previous stylesheet with one coordinated palette: warm ivory
  `#FFF8F0`, white, navy `#14213D`, cobalt `#3454D1`, coral `#FF6B4A`, peach
  `#FFE4D6`, lavender `#EEEAFE`, slate `#526078`, and warm-gray borders `#E5E1DC`.
  Added shared spacing, corner radii, restrained shadows, focus/hover states,
  native-control styling, and reduced-motion rules.
- Compact header with a MyNews wordmark, consistent local SVG icons, active
  navigation, and grouped profile control. At tablet/mobile widths the navigation
  becomes a second header row in normal document flow, covering no article actions.
- Compact greeting/date, wrapping topic links, prominent PDF download, readable
  Prepared at / News updated through values, and a concise shorter-edition notice.
  The lead headline is placed immediately after these compact controls, followed
  by supporting stories and section headings. First-viewport placement is a design
  intention supported by code inspection, **not a measured visual result**.
- Lead and supporting stories render once, in saved order, with their original
  titles, briefs, details, sources, reasons, and takeaways. One/two-story editions
  have explicit small-edition styling; no content is duplicated to fill a grid.
  Missing images produce text-first cards rather than oversized fake news banners.
- Real supplied images have defined aspect ratios, lazy loading for supporting
  images, eager loading for the lead, empty decorative alt text, and a compact
  failure caption. HTTPS publisher images are permitted by the screen CSP; scripts,
  forms, and other resources retain their existing restrictions. No image is fetched
  by a test or terminal verification command.
- Discover uses a responsive story grid with actual article-topic labels. Library
  uses dated archive cards with original read/download URLs and a saved-stories
  grid. Editor separates explicit interests, learned evidence, exclusions, and
  confirmed morning settings. Onboarding shares the new choices/progress styling;
  IDs, submitted fields, and autosave handlers remain intact.
- Screen dates are formatted from stored values in the selected reader's saved
  timezone, including date rollovers. Policy identifiers remain internal rather
  than appearing in edition metadata. A date-only edition remains its saved local
  calendar date. Unknown publication dates remain labeled unknown.
- No change to ingestion, recommendations, schema, worker, generation services,
  or edition snapshots. `templates/newspaper.html` and `pdf_export.py` are unchanged;
  neither loads the screen CSS/JavaScript.

Files changed: `app.py`, `static/style.css`, `static/screen.js`,
`templates/base.html`, `templates/shell.html`, `templates/_components.html`,
`templates/onboarding.html`, `tests/test_screen.py`, and this progress log.
`static/onboarding.js` is unchanged. The unrelated untracked
`MyNews_Architecture.png` was left untouched.

### Verification results

- **Passed:** 30 unittest checks (the existing regression suite plus four new
  screen-contract tests) on temporary databases. The PDF exporter was stubbed for
  route tests, so no Playwright/Chromium/browser process was invoked. This checks
  download routing, ownership responses, and content type, **not actual PDF bytes
  or rendering**.
- **Passed:** Flask test-client rendering of Paper, Discover, Library, Editor,
  profiles, real calibration, interest selection, and morning setup. Checks cover
  single/two/three-story rendering, long stored headlines, missing-image markup,
  original editorial order/content, CSRF/action/field contracts, timezone values,
  topic anchors, archive URLs, feedback events, saved state, and reading progress.
- **Passed:** existing snapshot order test renders the traditional newspaper
  template as an HTML string only. Screen and print template dependencies remain
  separate.
- **Passed:** Node syntax checks for both frontend scripts and Node DOM-stub
  checks for images that failed before script load, loaded successfully, or failed
  later. These are JavaScript unit checks, **not browser automation**.
- **Passed:** calculated text contrast for used palette pairs: white/cobalt
  6.30:1, navy/ivory 15.17:1, navy/peach 13.17:1, navy/coral 5.67:1,
  navy/lavender 13.57:1, slate/white 6.36:1, slate/lavender 5.40:1,
  cobalt/white 6.30:1, cobalt/peach 5.19:1. All exceed 4.5:1. Input/choice
  boundaries were darkened to `#8490A3` for non-text contrast against white.
- **Passed:** template/JavaScript references and responsive rules inspected in
  code for approximately 375px, 768px, and 1440px. Flexible widths, `minmax(0,1fr)`,
  wrapping actions, long-text wrapping, and single-column narrow layouts are
  present; there are no fixed navigation overlays or fixed story widths. This is
  a code check, **not proof of actual rendered fit**.
- **Passed:** `git diff --check`. No files staged, committed, or pushed.
- **Not run:** visual inspection, screenshots, actual image-network loading,
  physical/mobile-device interaction, or PDF browser rendering, per the brief.

Reproduce the browser-free unittest run in PowerShell:

```powershell
$env:TEMP = Join-Path (Get-Location) '.tmp'
$env:TMP = $env:TEMP
@'
import unittest
from unittest.mock import patch
suite = unittest.defaultTestLoader.discover('tests')
with patch('app.export_pdf', return_value=(b'%PDF-offline-route-test', False)):
    result = unittest.TextTestRunner(verbosity=1).run(suite)
raise SystemExit(not result.wasSuccessful())
'@ | .\.venv\Scripts\python.exe -
```

Do not run the unmodified full test command under the redesign's no-browser
restriction: one pre-existing PDF integration test invokes the actual renderer.

### Manual visual checklist

Restart Flask to load the new date filters and CSP. Then check at 375px, 768px,
and 1440px:

1. Lead story appears promptly on desktop; PDF/topic controls are easy to find.
2. Long headlines, one/two-story editions, missing/broken images, and expanded
   details fit without clipping or horizontal overflow.
3. Mobile navigation, profile switching, feedback, save/unsave, read/unread,
   archive/search/download, and editor controls remain comfortable to use.
4. Onboarding selections, Back/Next/Skip, refresh persistence, keyboard focus,
   validation, and morning confirmation remain clear.
5. Compare a saved edition's story order/content with its PDF; verify print output
   retains its separate traditional styling.

### Unrelated existing issues discovered (not changed)

- Visibility uses an explicit Mark seen POST. The repository has no automatic
  viewport/active-reading/source-open JavaScript instrumentation to preserve.
  The redesign retains the existing controls and events rather than claiming it
  implemented those missing behaviors.
- A temporary-database probe confirmed `/paper/save` accepts another reader's
  edition ID and stores that foreign association for the selected reader (302).
  `editions.set_saved()` does not check edition ownership. This is a pre-existing
  reader-isolation gap, independent of the visual changes; it needs a focused
  backend ownership fix and regression test. No production/runtime data was used
  or changed by the probe.

Inspect the changes, then commit and push to GitHub yourself. Suggested message:
`feat: redesign MyNews with a vibrant editorial interface`.
