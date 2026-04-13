## Working product definition

This is a **single-user, self-run developer journal** for technical learning and skill maintenance.

"Self-run" means the application runs locally on the user's machine. It is never hosted as a service and never supports multiple users. Cloud LLM access and other cloud APIs are acceptable — "self-run" refers to the application itself, not a requirement for full offline capability.

It has two connected but distinct engines:

**Learning engine**
Builds and maintains a visible knowledge profile from journal entries, quizzes, and user feedback. Its job is to understand what the user knows, where they are weaker, what they are currently exploring, and what they should likely learn next.

**Practice engine**
Generates weekly realistic micro-projects that keep the user’s hands-on skills sharp. Its job is not to mirror the journal topics, but to produce work calibrated to the user’s overall practical level.

---

# MVP Product Requirements Draft

## 1. Goals

The MVP should help a single user:

* capture technical reflections quickly, primarily through voice-to-text
* maintain a visible AI-derived understanding of their technical knowledge
* identify strengths, weak spots, current frontier, and next frontier
* receive quizzes that both reinforce known topics and probe adjacent ones
* receive curated reading recommendations from trusted sources only
* receive weekly realistic coding projects that help prevent skill atrophy

## 2. Non-goals

The MVP is not trying to be:

* a multi-user or hosted SaaS product
* a general life journal
* a career coaching tool
* a soft-skills tracker
* a progress analytics dashboard with time-series reporting
* a full profile-editing system
* a video or YouTube recommendation engine

---

## 3. Core product concepts

### Journal

The raw technical input from the user.

Input is primarily text, whether typed or dictated via the browser's built-in speech-to-text (Web Speech API). Voice-to-text is simply a convenience input method — the system never deals with audio files. All entries are stored and processed as text.

Edits and revised entries can exist. The system should preserve original entry history rather than destructively replacing it. The most recent version of an entry is the source of truth for the Knowledge Profile. Prior versions are kept for audit and history.

### Knowledge Profile

The visible, AI-derived layer built from the journal and other product interactions.

For MVP, it is read-only.

It should show:

* demonstrated strengths
* likely weak spots
* current frontier
* next frontier
* recurring themes
* unresolved or uncertain areas

### Current Frontier

Topics the user is actively learning, partially understands, or still needs reinforcement on.

### Next Frontier

Topics adjacent to the user’s demonstrated knowledge that the system believes are likely useful to probe or introduce next.

### Triage

Items the system cannot confidently resolve on its own, or items that appear contradictory, broken, or otherwise require review.

### Weekly Project

A realistic micro-project with starter code, tests, and work items designed to keep practical engineering skills sharp.

### Topic

A specific, identifiable piece of technical subject matter. Topics are the atomic unit of the Knowledge Profile.

Topics are not predefined. They are derived dynamically from journal entries, quiz interactions, and project outcomes using LLM inference. The system should aim for specificity — for example, "Go concurrency patterns" rather than just "Go" — while still being able to roll up into broader areas when useful.

The system should follow industry-standard taxonomies where applicable (e.g., established categories in software engineering, cloud infrastructure, databases, networking) to maintain consistency and avoid fragmentation. When a topic does not fit a known taxonomy, the system may create emergent topics, but should avoid unnecessary proliferation.

Each topic can carry related material: subtopics, adjacent topics, and prerequisite relationships. These relationships are inferred, not manually maintained.

---

## 4. Journal scope

The journal is **technical only** for MVP.

Allowed scope includes things like:

* things learned
* things the user wants to learn
* technical questions
* engineering reflections
* work-relevant technical context
* recurring technical pain points
* design or implementation thoughts

Excluded for MVP:

* general life journaling
* emotional journaling
* soft skills
* leadership coaching
* broad career planning

---

## 5. Knowledge Profile behavior

The Knowledge Profile should be directly visible to the user.

For MVP, the user does not need full direct editing of profile items, but the system should be designed so later versions could support manual overrides such as:

* “I already know this”
* “Do not focus on this topic”
* “This is not relevant”

For now, the main correction mechanisms should come through feedback, quiz outcomes, project outcomes, and triage resolution.

### Profile shape

The Knowledge Profile should be presented as a structured view organized by topic. Each topic entry should display:

* the topic name and brief description
* evidence strength (strong, developing, limited)
* category (demonstrated strength, weak spot, current frontier, next frontier, recurring theme, unresolved)
* confidence level of the system's assessment
* supporting evidence summary (which entries, quizzes, or projects contributed)

The profile should also surface high-level summaries: overall strengths, key gaps, what the user is currently exploring, and what the system recommends exploring next.

### Update cadence

The Knowledge Profile updates on a **daily** schedule:

* **Journal entries**: processed nightly; the system checks for new unprocessed entries each day
* **Quiz outcomes**: processed the night after the quiz is taken
* **Project outcomes**: processed the night a new project is issued (evaluating the prior project)

Profile updates are not real-time. This keeps LLM costs predictable and avoids noisy mid-day profile churn.

---

## 6. Evidence model

The system should not treat all topic signals equally.

### Strong evidence

A topic trends strong when there is repeated, coherent evidence such as:

* clear journal explanations
* repeated correct quiz performance
* good project outcomes involving the topic
* user feedback that generated material is too easy
* low contradiction and stable interpretation

### Weak or developing evidence

A topic trends weak or developing when there is evidence such as:

* repeated confusion in journal entries
* incorrect or partial quiz performance
* project struggles related to the topic
* repeated triage around the same area
* user feedback that material is too advanced

### Limited evidence

This should remain separate from weakness.

Sometimes the right conclusion is simply:

* not enough evidence
* inferred only
* adjacent topic, not yet demonstrated

This distinction is important so the profile does not become overconfident or misleading.

---

## 7. How the app decides what is “next”

The system uses **LLM inference** to determine what topics to introduce or reinforce next. There is no predefined topic map or skill tree.

The process works as follows:

* topics are derived dynamically from the user's journal entries, quiz results, and project outcomes
* the LLM identifies adjacencies, prerequisites, and natural next-steps based on what the user has demonstrated
* frontier topics are generated by analyzing gaps relative to the user's apparent trajectory and interests
* user feedback and feedforward signals steer the direction over time

This approach avoids the rigidity of a static curriculum while still producing coherent, non-random recommendations. The system should aim for consistency across sessions — it should not wildly shift recommendations unless new evidence warrants it.

---

## 8. Quizzes

Quizzes should use an **even blend** of:

* reinforcement of topics the user already touched or partially knows
* exploration of adjacent or next-frontier topics

That means quizzes serve two functions:

* help the user learn and retain knowledge
* help the system better profile the user’s real level

### Format

All quiz questions are **free-text response only**. No multiple choice, no true/false.

Free-text responses reveal the user's actual understanding, reasoning, and mental models — not just recognition. This gives the system much richer signal for profiling.

### Cadence

Quizzes are issued **weekly**, with a default of **10 questions** per quiz.

The question count is user-configurable. The system should allow the user to set their preferred number of questions per quiz through application settings.

### Evaluation

Quiz answers are evaluated by an **LLM-as-judge**. The judge should:

* assess correctness (full, partial, or incorrect)
* assess depth and nuance of the answer
* provide a short explanation for each evaluation — what was right, what was missing, what was wrong
* attach a confidence score to its own evaluation

Each quiz item should include the explanation in its results, not just a right-or-wrong verdict. That improves:

* trust
* learning value
* interpretability

---

## 9. Readings

Readings should be for **knowledge expansion**, not mainly for skill sharpening.

They should lean most heavily toward:

* next-frontier topics
* weak spots that need conceptual support
* deeper dives around strong areas when useful

The system must only recommend from an **editable allowlist** of trusted reading sources.

For MVP, reading recommendations should be text-based only. No video sources.

### Cadence

Reading recommendations are generated **weekly**, alongside quizzes. Each batch should include a small, focused set of recommendations (e.g., 3–5 links) rather than an overwhelming list. The count is not user-configurable for MVP but should remain a sensible, curated selection.

### Allowlist mechanics

The allowlist is a user-configurable list of approved source domains stored in the application database. It ships with a sensible default set of trusted sources. The user can add or remove entries through the application UI.

When generating reading recommendations, the LLM is constrained to only produce links pointing to domains on the allowlist. If a source is not on the list, the system must not recommend it — regardless of how relevant it may be.

### Initial default allowlist

The default allowlist should include trusted sources such as:

* official language documentation
* official framework documentation
* MDN (developer.mozilla.org)
* AWS docs (docs.aws.amazon.com)
* PostgreSQL docs (postgresql.org/docs)
* Python docs (docs.python.org)
* Go docs and Go blog (go.dev, go.dev/blog)
* Microsoft Learn (learn.microsoft.com)
* Martin Fowler (martinfowler.com)
* Thoughtworks (thoughtworks.com)
* selected established engineering blogs and official vendor engineering blogs

The guiding rule is:
**high-trust, reading-first, explicitly approved sources only.**

The MVP does not need to track whether the user actually read a recommendation.

---

## 10. Weekly projects

Weekly projects belong to the **practice engine**, not the learning engine.

They should **not** need to map directly to recent journal topics.

Instead, they should be calibrated to the user’s **overall practical level**.

### Weekly project goals

A weekly project should:

* feel like real engineering work
* include existing code
* include existing tests
* include explicit tasks or tickets
* include seeded bugs
* include missing features
* include refactors
* include optimizations
* be completable in part of a day to a couple of days
* avoid being so large that it feels like a second full-time job

### Weekly project difficulty

Difficulty should scale with the system’s estimate of the user’s practical level.

For MVP:

* start conservative
* adapt upward gradually based on performance and feedback
* do not automatically downshift
* allow the user to manually change or cap their level

That preserves challenge without making the system overly timid.

### Weekly project language

* **MVP weekly project support: Go only**

That keeps the first version focused and tractable. Later versions can expand to more languages.

### Project generation

Projects are **generated from scratch by the LLM** each week. Each generated project is a small, self-contained Go codebase that includes:

* Go source files with existing functionality
* Test files with existing test coverage
* A set of explicit tasks (fix bugs, add features, refactor, optimize)
* A README describing the project context and the work to be done

The LLM should aim to produce projects that feel like real-world engineering work — small services, CLI tools, data processors, API clients — not toy exercises or algorithmic puzzles.

If it becomes feasible to leverage existing open-source codebases as project seeds, that is an acceptable future enhancement, but the MVP should not depend on it.

### Project delivery

The application maintains a dedicated, git-ignored directory within the project structure (e.g., `workspace/projects/`) where generated projects are written. Each project gets its own subdirectory named by date or sequence.

### Project submission and evaluation

The user drives the project lifecycle:

1. A new project is issued weekly
2. The user works on it in the project directory
3. Before the next project is generated, the user submits their completed work along with optional feedback
4. The system evaluates the submission (code quality, task completion, test results) using an LLM judge
5. Evaluation results feed back into the Knowledge Profile and difficulty calibration
6. The next project is then generated

If the user does not submit before the next cycle, the system should note the skip and continue without penalizing difficulty.

### Initial practical level

On first use, the system runs an **initial profiling flow** to establish a baseline practical level for Go. This may include:

* self-assessment questions about Go experience
* a short diagnostic quiz
* optional: a small starter project to calibrate hands-on level

This prevents the system from starting completely blind and producing projects that are trivially easy or impossibly hard.

---

## 11. Triage

Triage exists for items the system cannot confidently settle on its own, or items that are severe enough to require attention.

### Triage sources

Triage items can be created by:

* the **profile update pipeline** — contradictions, low-confidence inferences, malformed entries
* **quiz evaluation** — ambiguous answers, scoring uncertainty, topic misclassification
* **project evaluation** — unclear submission results, contradictory performance signals

### User actions in MVP

The user can:

* accept
* reject
* edit
* defer

If deferred, the item remains unresolved.

### Severity model

Triage items should carry severity.

At minimum:

* low
* medium
* high
* critical

### Required behavior

* **high and critical** items should require user attention before the next profile update cycle
* **medium and low** items can remain unresolved without blocking the user

### Resolution mechanism

When a triage item requires attention, the user is presented with the item's context, the system's uncertainty, and a text input field. The user provides a clarifying response that resolves the ambiguity — for example, correcting a misinterpreted topic, confirming or denying a contradiction, or providing missing context. The system incorporates the resolution into the next profile update.

### What should count as critical or high-value triage

The strongest candidates are:

* contradictions in important profile conclusions
* malformed or nonsensical profile items
* unsafe or unusable structured output
* strong claims made with weak supporting evidence in a core area, when confidence appears overstated

Ambiguity-heavy judgments should be handled carefully. The triage system should avoid pretending uncertain interpretation is objective truth.

---

## 12. Evaluation philosophy

The system uses an **LLM-as-a-judge** pattern with confidence scoring and measurable performance on controlled tests.

This is an **internal quality assurance** principle — it measures how good the system's own judgments are, not how much the user has improved. This distinction keeps the product out of "progress analytics dashboard" territory (which is a non-goal) while still ensuring the AI's outputs are trustworthy and improvable.

The MVP should assume:

* profile quality and triage quality should be testable
* the system should attach confidence to important judgments
* severity and confidence should not be conflated
* the triage detector should be evaluated against controlled scenarios
* the product should be designed so its judgment quality can later be measured and improved with benchmark-style tests and scoring

That is especially important for:

* contradiction detection
* malformed profile detection
* overconfident inference detection
* triage prioritization quality

---

## 13. Feedback and feedforward

These are now first-class parts of the product.

### Feedback

Corrects the system’s current understanding.

Examples:

* too easy
* too hard
* relevant
* not relevant
* helpful
* not helpful

### Feedforward

Shapes what the system should do next.

Examples:

* more backend-oriented content
* deeper systems topics
* harder debugging tasks
* fewer certain topic types
* more exploration beyond comfort zone

### MVP feedback mechanism

Each generated item supports two levels of feedback:

* **Quick reaction**: thumbs-up / thumbs-down on the item as a whole
* **Optional text note**: a free-text field for richer directional input

The text note is where feedforward signals naturally live. A thumbs-down on a quiz question is feedback; writing "I want harder distributed systems questions" alongside it is feedforward. Both are captured on the same item, keeping the UX simple.

### Feedback attachment

Feedback attaches to **individual items**:

* individual quiz questions (not the quiz session as a whole)
* individual reading recommendations
* the weekly project as a whole, with optional per-task notes

This should apply to:

* quizzes
* readings
* weekly projects
* possibly other generated outputs later

---

## 14. First-run experience

On first launch, the system should guide the user through an **initial profiling flow** before normal operation begins. This establishes baseline context so the system does not start from zero.

The first-run flow should include:

* basic self-assessment of technical background and primary areas of expertise
* Go-specific experience level (since weekly projects are Go-only for MVP)
* a short diagnostic quiz to calibrate initial Knowledge Profile
* optional: selection of topics the user is currently interested in exploring
* optional: configuration of the reading allowlist (or accept defaults)

This flow should be lightweight — completable in 10–15 minutes — and should not feel like an exam. Its purpose is calibration, not evaluation.

---

## 15. Technical architecture

### Interface

The application is a **local web app**. The backend serves both the API and the frontend as static assets. The user launches the application locally and accesses it via the browser.

A web interface is the right fit because:

* the browser's Web Speech API provides zero-dependency voice-to-text input
* a web UI offers the richest display for the Knowledge Profile, quizzes, and project management
* it requires no platform-specific desktop framework
* it remains simple to launch and access

### Backend

**Python 3.12+ with FastAPI.**

Python is the best fit for this application because of:

* the strongest ecosystem for LLM integration and prompt engineering
* excellent async support for API calls (OpenRouter, etc.)
* mature database drivers (asyncpg, SQLAlchemy)
* rich text processing capabilities
* straightforward file I/O for project generation and delivery

### Frontend

**React with TypeScript.**

The frontend is built as a static SPA served by the FastAPI backend. It provides:

* the journal entry interface (text input + Web Speech API dictation)
* the Knowledge Profile viewer
* the quiz interface (question display, free-text answer input, results with explanations)
* reading recommendations display
* weekly project management (view tasks, submit work, see evaluation)
* triage resolution interface
* feedback controls on all generated items
* reading allowlist management

### Database

**PostgreSQL 16+ with the pgvector extension.**

PostgreSQL provides:

* robust relational storage for journal entries, profile data, quizzes, projects, triage, and feedback
* pgvector for vector similarity capabilities needed for topic matching, semantic search over journal entries, and future enhancements
* JSONB columns for flexible structured data (LLM outputs, evidence records, project metadata)

### LLM access

**OpenRouter** as the single API endpoint.

OpenRouter provides access to multiple models through one integration point. The system should be designed so that:

* different tasks can use different models (e.g., a smaller model for classification, a larger model for project generation)
* model selection is configurable, not hardcoded
* API costs are predictable due to the batch-oriented update cadence (nightly processing, weekly quizzes/projects)

### LLM observability

**Langfuse** for tracing and observability of all LLM operations.

Every LLM call should be traced through Langfuse, providing:

* full request/response logging for debugging and prompt iteration
* latency and token usage tracking per call
* trace grouping by pipeline (profile update, quiz generation, quiz evaluation, reading generation, project generation, project evaluation)
* cost visibility across models and tasks

This is essential for iterating on prompts, diagnosing quality issues, and understanding LLM cost distribution.

### Containerization

**Docker Compose** for local development and runtime.

The standard way to run the application is via Docker Compose, which manages:

* the Python/FastAPI application container
* the PostgreSQL + pgvector database container

This eliminates environment setup friction — the user needs only Docker installed to run the full stack.

### Scheduling

Scheduled tasks (nightly profile updates, weekly quiz/reading generation, weekly project issuance) are managed via **system cron jobs**.

During project initialization, the setup process should:

* check whether cron is available on the host system
* warn the user if cron is not found or not accessible
* offer to install the required crontab entries automatically
* document the expected cron schedule so the user can configure it manually if preferred

This keeps scheduling simple, transparent, and native to the host OS rather than requiring the application to implement its own scheduler or stay running as a daemon.

### Project directory

Generated weekly projects are written to a dedicated, **git-ignored** directory within the application structure (e.g., `workspace/projects/`). Each project gets its own subdirectory. This directory is excluded from version control so project work does not pollute the application repository.
