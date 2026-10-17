# MyNews build progress

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
