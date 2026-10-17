# MyNews build progress

## Phase 1 — completed, 17 October 2026

Implemented only the application foundation, persistent local reader profiles, and choice-based onboarding. The complete `MYNEWS_PROJECT_REFERENCE.md` was read before editing and preserved. No existing application or Git history was present; no `AGENTS.md` was found in the workspace or checked ancestor locations. A local Git repository was initialized on `main` for review; no files were staged and no commit, push, or GitHub remote was created.

### Completed behavior

- Flask/Jinja application with system fonts, local static CSS, and a small vanilla JavaScript enhancement. No frontend build framework, external assets, Docker, or service layer.
- Responsive navigation for Today's Paper, Discover, My Library, and My Editor. Empty pages accurately explain future capabilities. No invented articles, statistics, generation buttons, or inactive controls.
- Optional/generated local profile names, selection through CSRF-protected POST, session-selected ownership, persistent profiles/completion/resume stage, separate preferences for each reader.
- Eight onboarding stages with optional skips, visible progress, Back/Next, and clear single/multiple choice labels. Every one of the twelve categories has adaptive subtopics, maintained in `taxonomy.py`.
- Regions include Worldwide and selectable countries/regions. Worldwide is exclusive; skipped/empty regions default to Worldwide.
- Clearly fictional calibration examples are isolated in `setup_examples.json`, shown only during setup, and saved as explicit topic/subtopic preferences. `calibration_candidates()` is the replacement point for Phase 2 real cached articles.
- Browser timezone suggestion, an IANA timezone selector, native time input, server-side validation, and required explicit final confirmation. Valid schedule drafts survive refresh without completing setup. Back remains available if unfinished schedule input is invalid.
- Optional age/education never infer interests or expertise. Skipped interests persist `general_interest: true`. Completion welcomes the reader and states that an edition has not been generated.
- Draft autosave on choice changes, ordered so a stale draft does not overwrite a later navigation submission. Back/Next/Skip also persist without JavaScript. Refresh after the saved status appears; a network request interrupted before it finishes is not a committed save.
- My Editor displays saved explicit choices and confirmed morning settings; setup can be reviewed through the existing wizard. Saving edits marks onboarding incomplete until the final confirmation is completed again.
- Only two SQLite tables (`readers`, `preferences`), with foreign keys, checks, parameterized queries, transactions, and schema version 1 via `PRAGMA user_version`. No future article/edition/learning schema.
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
- All four navigation links work; My Editor shows the correct selected reader's preferences, and Discover/Library accurately show empty states.
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

### What Phase 2 can build on

Use the existing taxonomy, session-selected profile ownership, validated persistent preferences, transaction/schema-version mechanism, and candidate-source function. Add real sourced article ingestion/cache/content preparation/embeddings in Phase 2, replacing fictional setup candidates with real cached headlines. Keep fictional examples out of live news and preserve the no-key path. Do not begin LinUCB/behavioral learning until Phase 3.
