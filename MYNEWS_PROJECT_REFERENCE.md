# MyNews Project Reference

Version 1.0 · 17 October 2026 · Requirements and six Codex implementation prompts

## 1. Purpose and authority

MyNews is a personal morning newspaper for a general audience. It learns the reader's interests through choice-based onboarding and subsequent consumption, then selects a fresh daily edition from multiple real news sources. Readers use an interactive website or download the same editorial content as a traditional newspaper PDF.

This file incorporates the NaSCon'26 brief and the user's later decisions. It supersedes the earlier discussion draft wherever they differ. Onboarding has no free-text interest questions, there is no reading-time selector, and the web design does not have to resemble a printed newspaper.

Place this file at the repository root as MYNEWS_PROJECT_REFERENCE.md. Codex must read it before every step, inspect the existing project and AGENTS.md instructions, and record outcomes in BUILD_PROGRESS.md. The six prompts below are to be run sequentially. This file is a build specification, not an already implemented application.

## 2. Fixed decisions and constraints

- Name: **MyNews**.
- Audience: general readers with broad topical interests.
- One developer using Codex; six-hour implementation target.
- Local hosting first, with Windows PowerShell setup instructions.
- No mandatory paid APIs, cloud services, or generative LLM.
- Free TheNewsAPI key is optional for the RSS-only path.
- Internet is needed for live news and initial model/browser downloads.
- No external training dataset is required.
- A pretrained embedding neural network runs locally; its weights initially remain fixed.
- The reader profile and contextual-bandit policy update from actual app feedback.
- Approximately 10–15 minutes for the main edition; optional detail can take longer.
- Reader selects timezone and a morning-ready time during profile setup.
- Store all important state persistently.
- Vercel/cloud deployment is deferred. SQLite persistence, model files, Chromium and a background worker need a hosting plan before public deployment.
- The six-hour allocations are targets, not guaranteed completion times. Report blockers and cut optional polish before cutting required behavior.

### Required foundation

1. Smooth onboarding creates useful first recommendations.
2. Real articles from multiple sources retain publication times and original links.
3. The website offers complete reading with headlines first and expandable details.
4. The same saved daily edition is downloadable as a traditional newspaper PDF.
5. Earlier editions remain accessible.
6. Feedback and behavior improve future recommendations.
7. Daily editions are generated according to each reader's saved schedule while the local worker is running.

### Agreed signature features

- Discover: additional recommendations that adapt after feedback.
- My Editor: understandable and editable selected/learned interests, exclusions, and reset.
- Recommendation explanations based on actual selection evidence.
- Controlled discovery of significant developments in related interests.
- Saved stories, resume reading, and short edition takeaways.
- A fixed approximate 10–15 minute main edition, without duration settings.

### Deferred features

Article chat, story-following timelines, semantic archive search, audio, multilingual generation, external account imports, notifications, custom neural training, and deployment. Do not build these during the six steps.

## 3. Onboarding and main pages

### Choice-based onboarding

Use tappable options, clear selected states, progress, back navigation, and skip where appropriate. Preserve selections when going back. Show subtopics progressively rather than presenting an enormous taxonomy on one screen. No interest essays or conversational text fields.

| Stage | Choices and behavior |
|---|---|
| Age range | Optional Under 18, 18–29, 30–49, 50+, plus Skip |
| Education | Optional School, College, Undergraduate, Postgraduate, Other, Prefer not to say |
| Current activity | Multi-select Studying, Employed, Freelancing, Business owner, Job seeking, Retired, Other |
| Main interests | Multi-select Technology, Science, Business, Sports, Entertainment, Politics, Health, Education, Environment, Culture, Travel, Gaming |
| Subtopics | Adaptive options under chosen topics, such as AI, Software, Gadgets, Robotics; or Cricket, Football, Tennis |
| Region | Select country/region interests or Worldwide; actual coverage depends on sources |
| Headline calibration | A few real selectable headlines based on topic choices; allow Skip |
| Morning setup | Confirm an IANA timezone from a selector and choose morning time with a native time control |

Browser-detected timezone can be a suggestion; save the user's confirmed choice. Optional age and education provide context, not assumptions about expertise or interests. In the first version they need not influence ranking. Explicit selections and actual behavior matter more.

If all interests are skipped, use a balanced general edition and acknowledge limited personalization. Valid timezone and morning-time defaults must be visible and confirmed. A normal optional profile name is acceptable; it is not an interest questionnaire.

Before ingestion works, headline examples may be clearly labeled as temporary. Replace them with real cached stories in step 2. Do not pass examples off as current news.

### Main pages

| Page | Included behavior |
|---|---|
| Today's Paper | Lead headlines, sections, briefs, expandable details, sources/dates, feedback, saving, progress, takeaways, PDF download |
| Discover | Additional recommendations, updated after feedback on the next request; no disruptive reshuffle while reading |
| My Library | Past editions by date, saved stories, simple title/summary search, resume, old PDF downloads |
| My Editor | Selected and learned interests, explicit exclusions, reset learned state, timezone and morning-time settings |

Use a modern responsive web layout. Traditional columns belong to PDF output. Include keyboard focus, readable text, mobile navigation, image fallbacks, loading/error/empty states, and no decorative controls that do nothing. Prefer system fonts and local assets over CDN dependencies.

## 4. Implementation choices

Use one Python application with ordinary templates and static assets, not microservices.

| Concern | Initial choice |
|---|---|
| Web | Flask, Jinja, HTML/CSS, small vanilla JavaScript modules |
| Database | Python sqlite3, parameterized queries, foreign keys, explicit transactions |
| News discovery | TheNewsAPI Top Stories and All News endpoints; verified publisher RSS/Atom |
| Feed parsing | Feedparser |
| HTTP | Requests with finite timeouts, bounded retries and redacted errors |
| Text extraction | Trafilatura for permitted accessible publisher pages when needed |
| Embeddings | Sentence Transformers all-MiniLM-L6-v2, downloaded once and run locally on CPU |
| Online learning | Small persisted LinUCB policy using NumPy |
| Briefs/details | Deterministic extractive selection from source text; no mandatory generative LLM |
| PDF | Playwright Chromium with a separate newspaper print template |
| Scheduling | One separate local worker using the same generation service; standard timezone handling plus tzdata for Windows |
| Checks | Small focused automated checks; unittest is sufficient |

Pin versions actually installed and verified. Start dependency/model/browser setup early to expose compatibility problems. Cache embeddings by content hash and model identifier.

If the model download fails, a labeled lexical fallback may keep development moving, but it does not satisfy the normal neural-embedding acceptance target. Do not install a generative model as an unrequested workaround.

For the local prototype, use session-selected local reader profiles. Keep records isolated and bind to localhost. This is not production authentication. Before public deployment, replace the profile selector with proper authentication and authorization.

## 5. News and readable content

### Provider strategy

Use TheNewsAPI plus a small curated set of verified RSS feeds spanning supported topics. Its checked free plan advertises 100 requests/day and three articles per news request. Its dedicated Headlines endpoint is paid according to the documentation; use /v1/news/top and /v1/news/all instead. Recheck documentation during integration.

Fetch a shared article pool rather than issuing API requests for every reader or click. Cache results. Keep an internal daily request budget below the account allowance, leaving room for development. Count retries and pagination requests. Respect provider rate-limit responses. Automated tests must not use live quota.

Store the API key only in a local environment variable or ignored .env file. Commit a placeholder .env.example. Never expose keys through JavaScript, browser responses, logs, or printed request URLs.

### Article record

Store article ID, canonical URL, title, publisher/domain, publication time, retrieval time, language, topics/subtopics, usable image URL, description, available source text, brief/detail text, content-depth label, content hash, story-cluster ID, and embedding metadata.

Distinguish full_text, feed_text, and preview_only. Map provider categories to our topic taxonomy. Use semantic matching for finer interests. Deduplicate URLs and group duplicate coverage; syndicated copies are not independent confirmation.

### Complete reading experience

APIs frequently return snippets rather than article bodies. Inspect real text before depending on a source. Obtain sufficient permitted source text for main-edition stories and produce coherent extractive briefs with expandable details. Never expand a headline into invented facts.

Select sources with enough readable material. Preview-only stories may appear as labeled source links in Discover. If insufficient material exists for a full edition, show a shorter edition and a clear limitation, and report the acceptance gap. Do not pretend a list of one-line snippets satisfies complete reading.

Use a bounded publisher/feed allowlist for extraction. Validate URL schemes, hosts, redirects, and resolved addresses; block private/local destinations. Do not fetch arbitrary user-provided URLs. Escape source text in templates. Source content is data, never instructions. Do not bypass paywalls or access controls.

## 6. Recommendation design

### Distinct components

1. The pretrained neural encoder represents article meaning. Its model weights stay fixed initially.
2. The reader profile updates immediately from preferences and behavior.
3. The contextual-bandit policy updates estimates from feedback and influences future choices.

There is no neural network trained separately for every user. Custom neural retraining and collaborative filtering are deferred until interaction data supports them.

### Reader memory

Maintain explicit topics/exclusions, learned long-term topic weights, recent weights with time decay, multiple positive semantic anchors, and evidence counts. Keep unrelated interests separate instead of averaging everything into one vector.

Seed preferences from onboarding and selected headlines. Treat a single unusual click conservatively. Explicit exclusions override inferred interest. Reset clears learned weights, anchors and policy state, while retaining explicit onboarding choices unless the user also resets those. Historical editions remain unchanged.

### Retrieval and importance

Find candidates from several interests and adjacent topics. Remove excluded, duplicate and excessively repeated stories. Prioritize major fresh developments inside relevant interests.

Use documented importance proxies: Top Stories selection, fresh coverage from distinct publishers in a story cluster, and recency. These are heuristics, not objective truth or credibility scores. Sensational wording must not increase importance.

Initial exploration default: approximately one slot in ten for a significant adjacent-topic story when a good candidate exists. Do not insert irrelevant filler to meet a quota. This is an implementation default, not a user reading-duration setting.

### LinUCB policy

Use LinUCB with positive regularization and a documented, versioned low-dimensional feature vector. Features can include topic affinities, semantic match to recent and long-term anchors, explicit matches, freshness, significance, and prior exposure. Avoid a large covariance matrix over raw embedding dimensions.

Persist one policy state per reader for this prototype. This provides per-reader adaptation but limited cross-reader learning; onboarding supplies cold-start relevance. Start from regularized neutral estimates. Use linear solves rather than repeatedly computing explicit matrix inverses.

Combine expected reward and uncertainty using the standard LinUCB selection rule inside eligible candidate sets. Editorial relevance/diversity constraints still apply. Store the actual score components and explanation. Do not label a static weighted sorter as reinforcement learning: tests must demonstrate parameter updates and changed future scores.

### Feedback defaults

These are tunable engineering defaults, not measured probabilities:

| Evidence | Initial effective reward |
|---|---:|
| More like this | +1.0 |
| Less like this | -1.0 |
| Save, without explicit rating | +0.6 |
| Conservative meaningful active reading | Up to +0.3 |
| Open original source, without stronger signal | +0.1 |
| Explicit skip | -0.1 |
| Unseen or no observed response | Unknown; no automatic negative update |

Use one effective reward per impression, with explicit rating taking precedence and otherwise the strongest eligible signal. Do not add every event's reward together. Repeated clicks must not multiply learning.

Save the feature vector at recommendation time. Add its covariance contribution once when an eligible outcome arrives. If later feedback changes the effective reward, adjust the reward contribution by the difference without adding covariance again. Deduplicate event IDs. Bound reader-profile updates similarly. Save/unsave and more/less toggles must behave consistently.

Reading requires a visible active tab plus conservative time/scroll evidence. It is an estimate, not proof of comprehension. A PDF download is not evidence that every story was read. External publisher reading is not reliably observable.

### Event records

Record recommendation ID, reader, article, surface, position, timestamp, policy and feature versions, feature snapshot, score/reason, actual visible impression, event ID/type/time, effective reward and processing status.

LinUCB may be deterministic. Mark that honestly and leave selection propensity unavailable unless an actual randomized policy defines it. Do not invent probabilities or claim unbiased counterfactual evaluation.

Use labeled deterministic fixtures to show learning and an isolated simulated history for demo profiles. That demonstrates mechanism, not proven real-world recommendation quality. Compare with a topic-only baseline as real feedback accumulates.

## 7. Edition and PDF contracts

### Saved edition

Each edition stores reader, local edition date, timezone/schedule snapshots, actual generation time, content cutoff, status, profile/policy versions, and ordered story snapshots.

Each item stores section, title, brief, detail text, dates, original links, selection explanation and takeaway. The website and PDF render these same snapshots. They must not query mutable article text or generate new summaries during PDF export.

The main edition targets 10–15 minutes based on actual word count and a documented reading-speed assumption. Detail expansion can take longer. Story count depends on available content. Do not pad facts or use a reading-time selector.

Today's edition remains stable after feedback. Discover and the next edition adapt. If a material correction is made, label the revision and keep web/PDF versions aligned. Automated correction tooling is outside the initial build.

### Scheduling

Store timestamps in UTC and reader timezones as IANA identifiers. Use one separate local worker. Pre-fetch source content ahead of due times and perform a bounded refresh near the scheduled cutoff. The chosen morning time is the target ready time; display actual cutoff and generation time.

Use a database uniqueness constraint for one successful edition per reader/local date and an atomic generation claim. Duplicate worker/manual requests must not create duplicates. Retry bounded recoverable failures and retain the last successful edition.

If the computer is off, generation cannot run. On restart, catch up today's due edition; show actual timing and do not fabricate missed historical editions. Timezone changes affect future editions. Document DST handling: first occurrence for ambiguous times, first valid instant after a nonexistent scheduled time.

### PDF and archive

Render a dedicated traditional newspaper template with masthead, date, lead story, columns, sections, readable typography, page numbers and original sources. Include the saved briefs and expanded detail. Omit web navigation and feedback controls. Make remote images optional.

Serve actual PDF bytes with an appropriate filename/content type. Cache PDFs by edition/revision. Previous editions remain accessible and downloadable after profile changes and restarts.

## 8. Storage and implementation boundaries

Use a few modules for web routes, storage, news, recommendations, edition generation and the worker. No vector database, message broker, frontend build framework or separate recommendation service is needed for this scale.

Logical records: reader profiles, articles, optional story groups, recommendations/impressions, feedback events, policy state, editions/items, saved stories, progress, ingestion/quota state, and generation claims. JSON fields are acceptable for compact vectors and profile attributes; enforce ownership and uniqueness in SQLite.

Validate writes, use parameterized queries, protect state-changing browser requests and escape content. Resolve the reader from the selected session profile; never trust a client-supplied reader ID alone for ownership.

Ignore .env, virtual environments, downloaded models, database files, generated PDFs, caches, and private logs in Git. Track safe configuration, schema, source code, README, reference, progress notes, and labeled test fixtures. Keep simulated histories separate from live analytics. Fictional news belongs only in tests.

## 9. Six build steps

These steps build the platform. They exclude slides, Loom recording and submission preparation.

| Step | Time target | Working outcome |
|---|---:|---|
| 1 | 45 minutes | App foundation, persistent profiles, choice-based onboarding |
| 2 | 70 minutes | Real news, usable text, normalization, shared cache and embeddings |
| 3 | 85 minutes | Learning engine, persisted bandit, events, Discover and My Editor |
| 4 | 70 minutes | Stable personalized editions and interactive reading |
| 5 | 40 minutes | Traditional PDF, archive, saved stories and resume |
| 6 | 50 minutes | Timezone scheduling, recovery and end-to-end verification |
| Total | 360 minutes | Six-hour target |

### Before the first prompt

Create the hackathon GitHub repository at the start, as required by the brief, and place this file at its root. If an existing checkout is supplied, preserve its history and unrelated work.

Make an initial commit containing the reference and ignore rules; push when the remote is configured. Obtain a free TheNewsAPI key for step 2 if desired and keep it in the local environment, never in a prompt.

Commits are version history, not CI/CD by themselves. Step 6 adds a small offline CI check; automated deployment is outside this scope.

## 10. Copy-ready Codex prompts

Run one prompt at a time. Review its results and complete its checkup before moving on. Each prompt requires a GitHub commit reminder. Do not implement all six simultaneously.

### Prompt 1 — Foundation and onboarding

```text
Read MYNEWS_PROJECT_REFERENCE.md completely. Inspect the repository and AGENTS.md before editing. Implement only step 1 of MyNews. Preserve unrelated work and Git history.

Build a local Flask app with SQLite persistence, session-selected local reader profiles, and responsive navigation for Today's Paper, Discover, My Library and My Editor. Mark unfinished pages honestly.

Implement the choice-based onboarding wizard in the reference: optional age/education/activity, broad interests and adaptive multi-select subtopics, region, headline selection, confirmed timezone, and native morning-time control. No free-text interest questions or reading-duration options. Preserve back-navigation state and handle skip/default behavior. Clearly label temporary example headlines until step 2 provides real ones.

Provide database initialization and simple schema version tracking, .gitignore, safe .env.example, pinned verified dependencies, README Windows PowerShell commands, and BUILD_PROGRESS.md. Bind to localhost. Prepare model/Chromium installation instructions and check environment compatibility early. Do not implement future-step behavior or require a news key for onboarding.

Check persistence after restart, invalid timezone/time rejection, back/skip behavior, two-reader isolation, and desktop/mobile layout. Add focused profile persistence/validation checks and run them. Report checks that cannot run.

Finish with implemented behavior, changed files, exact run/check commands and outcomes, remaining issues, and the next step. Update BUILD_PROGRESS.md. End by reminding me to inspect git status and staged changes, exclude secrets/runtime files, commit and push to GitHub. Suggested message: feat: add MyNews foundation and choice-based onboarding. Do not commit/push automatically or start step 2.
```

**Checkup:** Complete onboarding, restart the app, and confirm preferences and schedule persist. Try the wizard on a narrow screen.

**GitHub reminder:** Review git status and git diff --cached, then commit and push. Suggested message: feat: add MyNews foundation and choice-based onboarding.

### Prompt 2 — Real news and content understanding

```text
Read MYNEWS_PROJECT_REFERENCE.md and BUILD_PROGRESS.md, inspect step 1, and implement only step 2. Reuse existing storage/configuration. Fix and report blocking prior defects.

Integrate TheNewsAPI's free-compatible Top Stories/All News endpoints with a server-side key, bounded budget, timeouts and rate-limit handling. Check current documentation. Add a small set of verified real RSS feeds across broad interests, with a working no-key path. Fetch and cache shared results; never call live APIs in automated tests or print key-bearing URLs.

Normalize source URLs, publisher, dates, language, topics, content hashes and depth labels. Deduplicate articles and group related coverage. Inspect actual source text and obtain sufficient permitted text for readable briefs and expanded details. Use safe bounded extraction and deterministic extractive summaries. Do not fabricate detail from snippets or bypass blocked content. Report content-depth and regional coverage gaps.

Run all-MiniLM-L6-v2 locally and cache embeddings by content hash/model. Document CPU startup behavior. Do not train it. If download fails, label any lexical fallback accurately. Replace temporary onboarding examples with real cached headline choices and provide a skip path if news is unavailable.

Check deduplication, missing dates, UTC handling, no-key operation, inadequate content, feed/provider failure, quota enforcement, unsafe extraction URLs, and embedding reuse. Do a small live ingestion if access exists; otherwise report the limitation. Preserve dates in genuine cached news and isolate synthetic fixtures. Update README/BUILD_PROGRESS.md.

Finish with actual completion/check outcomes and a reminder to inspect the staged diff, exclude secrets/caches/databases, commit and push to GitHub. Suggested message: feat: ingest and prepare real news content. Do not commit/push automatically or start step 3.
```

**Checkup:** Compare several stories with their original sources. Verify dates, usable text, broad interest coverage, and absence of API secrets in browser responses/logs.

**GitHub reminder:** Commit and push after reviewing the diff. Suggested message: feat: ingest and prepare real news content.

### Prompt 3 — Adaptive recommendations

```text
Read the full reference and BUILD_PROGRESS.md. Implement only step 3 using the existing article pool and embeddings. Build real persisted learning, not a static sorter with learning labels.

Implement explicit/learned topic preferences, recent-interest decay, multiple semantic anchors, exclusions and evidence counts. Retrieve candidates across several interests, prioritize major relevant developments, and include bounded adjacent-topic exploration. Explain recommendations from actual selection evidence.

Implement the small NumPy LinUCB policy with positive regularization, a documented versioned feature schema and per-reader persistent state. Store recommendation-time features. Log actual impressions and feedback; implement effective reward precedence, event deduplication and later reward corrections without duplicate covariance contributions. Handle saves, more/less feedback, source opens, skips and conservative active-reading evidence. Unseen stories are not dislikes. Record deterministic-policy status honestly rather than inventing propensities.

Make Discover functional and responsive to feedback on the next request. Implement My Editor's selected and learned interests, exclusions, schedule editing, and learned-state reset. Honor explicit preferences and isolate reader data. Persist learning across restart.

Use labeled deterministic fixtures to verify cold start, positive/negative score changes, actual policy-parameter changes, event duplication, later reward correction, exclusions, reset, multiple interests and reader isolation. Show later recommendations changing after feedback, without claiming real-world accuracy. Document the exact feature vector and initial rewards.

Update BUILD_PROGRESS.md with results and gaps. End with a reminder to review the diff, commit and push to GitHub. Suggested message: feat: add adaptive recommendations and feedback learning. Do not commit/push automatically or start step 4.
```

**Checkup:** Give one of two profiles positive and negative feedback. Confirm its next scores and recommendations change, its policy state survives restart, and the other reader is unaffected.

**GitHub reminder:** Commit and push the working learning loop. Suggested message: feat: add adaptive recommendations and feedback learning.

### Prompt 4 — Daily editions and web reading

```text
Read MYNEWS_PROJECT_REFERENCE.md and BUILD_PROGRESS.md. Implement only step 4, reusing the content and recommendation services.

Create manual/first-edition generation as a service the future worker can call. Save reader-specific dated editions with ordered immutable story snapshots, cutoff/generation times, profile/policy versions, sections, sources, briefs, details, recommendation reasons and takeaways. Use transactional claims and uniqueness constraints to prevent duplicate reader/date editions. Feedback must not overwrite published editions.

Build Today's Paper with important relevant headlines first, topic sections, expandable details, source links/dates, image fallbacks, feedback, saving, reading progress and takeaways. Wire actions to actual persistence and step 3 events. Register impressions only when stories become visible. Target 10–15 minutes for the main briefs using actual word counts and a documented estimate. Optional detail can be longer. No reading-time selector or fabricated padding.

Generate the first edition after onboarding when content is available. Handle loading, no content, generation failure, already-generated and shorter-edition states honestly. Keep Discover adaptive while today's edition stays stable. Use a modern responsive web layout; print columns are reserved for step 5.

Check personalized results for two different readers, idempotent generation, unchanged old snapshots after article/profile updates, persistent saving/progress, and usable mobile details/navigation. Update README/BUILD_PROGRESS.md with actual checks and gaps.

End with a completion report and reminder to inspect staged changes, commit and push to GitHub. Suggested message: feat: build personalized daily web editions. Do not commit/push automatically or start step 5.
```

**Checkup:** Read an edition end to end. Change preferences, reopen the edition, and confirm its content is unchanged. Compare expanded details to the original reporting.

**GitHub reminder:** Commit and push. Suggested message: feat: build personalized daily web editions.

### Prompt 5 — PDF and archive

```text
Read MYNEWS_PROJECT_REFERENCE.md and BUILD_PROGRESS.md. Implement only step 5 using saved edition snapshots as the editorial source for both web and PDF.

Create a traditional newspaper print template: masthead, date, lead story, sections, readable columns, page numbers and original source references. Generate real downloadable PDF bytes with Playwright Chromium. Preserve the saved story order, briefs and expanded details. Omit interactive controls. Do not rerank, regenerate summaries or read mutable article text during export. Cache PDFs by edition/revision and avoid blocking on remote images.

Implement My Library with previous editions by date, saved stories, simple title/summary search, resume-reading links and old PDF downloads. Apply ownership checks and useful empty/error states. Ensure previously saved stories and progress appear. Document browser installation and PDF troubleshooting.

Check PDF signature/content type, story order and content against the saved edition, and old downloads after preference changes. Open and visually inspect every page of a multi-page PDF for clipping, overlap, columns, long headlines and source references. Check mobile/desktop library views and archive persistence/ownership. Record actual results in BUILD_PROGRESS.md.

End with a completion report and reminder to inspect the diff, commit and push to GitHub. Suggested message: feat: add newspaper PDF export and edition archive. Do not commit/push automatically or start step 6.
```

**Checkup:** Open the downloaded PDF, compare the stories with the website, and download an older edition. Inspect every page visually.

**GitHub reminder:** Commit and push. Suggested message: feat: add newspaper PDF export and edition archive.

### Prompt 6 — Scheduling and full verification

```text
Read MYNEWS_PROJECT_REFERENCE.md and BUILD_PROGRESS.md. Implement step 6 and resolve concrete defects preventing the agreed platform from working end to end. Do not add deferred features, deployment or presentation work.

Add one separate local worker that reuses ingestion/generation services. Compute due editions from each reader's saved IANA timezone and morning-ready time. Prepare shared content ahead of schedule and perform bounded refresh near cutoff. Persist claims/status, prevent overlapping duplicates, retry recoverable failures with bounds, and preserve the previous successful edition. Handle restart catch-up for today, timezone changes and the documented DST policy. Show actual cutoff/generation times and the local-machine-running requirement.

Finish error/empty states and usability across onboarding, reading, Discover, My Editor, PDF and Library. Add isolated labeled demo profiles with simulated interactions and real dated cached news when available. Fictional stories remain only in test fixtures. Complete Windows setup, model/browser installation, optional API-key configuration, app/worker startup, tests, demo/reset instructions and known limits in README.

Run a deterministic end-to-end check on a temporary fresh database: two readers, onboarding, fixture ingestion, feedback, persisted policy learning, editions, PDF, archive and restart. Test scheduling with an injected clock rather than long sleeps; include duplicate generation claims, timezone date boundaries, DST, provider failure and quota exhaustion. Separately run a real-source/model smoke check if network/credentials permit. Inspect mobile layout and every page of the actual PDF. Report passed, failed and not-run checks separately.

Add a minimal GitHub Actions offline CI check if repository policy permits. Do not require live news or large model downloads on every CI run; mock inference there and document a separate real-model check. No deployment automation. Fix concrete failures and avoid optional testing once the agreed scope is sufficiently verified.

Finish BUILD_PROGRESS.md with requirement-by-requirement status, actual check evidence, remaining gaps and startup commands. End with a reminder to inspect staged files/secrets, commit and push to GitHub. Suggested message: feat: finish scheduling and verify MyNews end to end. Do not commit/push automatically or declare incomplete requirements finished.
```

**Checkup:** Run the app and worker, temporarily choose a nearby ready time, and verify a single correctly dated edition. Restart the worker and confirm no duplicate. Try the app with live news unavailable.

**GitHub reminder:** Commit and push the verified platform. Suggested message: feat: finish scheduling and verify MyNews end to end.

## 11. Final acceptance checklist

- [ ] Onboarding uses choices and supports timezone/morning time.
- [ ] No free-text interest questions or reading-duration selector.
- [ ] Real sourced content supports actual reading, not only headlines.
- [ ] RSS works without a key; no paid service is mandatory.
- [ ] Local neural embeddings work; any fallback is labeled.
- [ ] Profiles and policy parameters update, persist and affect selection.
- [ ] Major relevant stories lead; exploration is bounded and related.
- [ ] Discover, My Editor, exclusions and reset work.
- [ ] Daily editions remain stable with clear cutoff and generation times.
- [ ] Web and PDF share story content/order with different layouts.
- [ ] Archive, saves, progress and PDF downloads survive restarts.
- [ ] Scheduling handles timezones, recovery and duplicate prevention.
- [ ] Mobile reading and loading/error/empty states are usable.
- [ ] Demo/test data is labeled and separated from live behavior.
- [ ] Checks report actual evidence and distinguish mechanism from proven recommendation quality.
- [ ] Git has incremental commits and contains no secrets/runtime data.

## 12. References and integration checks

Requirement source: user-supplied NaSCon'26 Problem Statement.pdf and subsequent decisions in this conversation. The brief requires a new repository at the start of the hackathon with monitored commits. Submission deliverables are outside this six-step platform plan.

Technical references reviewed during planning:

- TheNewsAPI pricing: https://www.thenewsapi.com/pricing
- TheNewsAPI documentation: https://www.thenewsapi.com/documentation
- MiniLM model: https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2
- Feedparser: https://feedparser.readthedocs.io/en/latest/introduction/
- Playwright PDF: https://playwright.dev/python/docs/api/class-page#page-pdf
- Contextual-bandit news recommendation research: https://arxiv.org/abs/1003.0146
- Instagram Explore design: https://engineering.fb.com/2023/08/09/ml-applications/scaling-instagram-explore-recommendations-system/

Check source availability, content depth, extraction permissions, provider limits, actual installed versions and machine performance during implementation. This reference selects the approach; it does not claim those runtime checks have passed.

