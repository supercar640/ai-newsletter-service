# AGENTS.md

> Baseline guide for any AI coding agent working on this repository
> (Claude Code, Codex, Cursor, Cline, Aider, etc.).
> Agent-specific guides (e.g. [`CLAUDE.md`](CLAUDE.md)) extend this baseline.
> When they conflict, the spec wins, then this file, then the agent-specific file.

---

## Project

| | |
|---|---|
| **Name** | AI Newsletter Service |
| **One-liner** | Internal AI intelligence newsletter automation. Collects AI news/RSS/YouTube, classifies into two tracks (expert news / practical insight), drafts with LLMs, requires human review, then emails. |
| **Spec (source of truth)** | [`plan/ai_newsletter_service_plan.md`](plan/ai_newsletter_service_plan.md) |
| **Approved implementation plan** | `C:\Users\user\.claude\plans\wondrous-cooking-quill.md` |
| **Status** | Greenfield. Phase 1 (MVP) in progress. |

---

## Stack

| Concern | Tool |
|---|---|
| Runtime | Python 3.12 |
| Package manager | `uv` |
| CLI | Typer |
| DB | SQLite + SQLAlchemy 2.0 + Alembic |
| LLM | Anthropic SDK — `claude-sonnet-4-6` for processing, `claude-opus-4-7` for final writing |
| RSS / HTTP | feedparser, httpx |
| Templating | Jinja2 (Markdown + HTML email) |
| Settings | pydantic-settings + `.env` |
| Logging | structlog |
| Email | smtplib (Gmail SMTP, app password) |
| Test | pytest, respx (HTTP mock), freezegun (time) |
| Lint / format | ruff |

---

## Setup

```bash
uv sync
cp .env.example .env       # fill in keys
uv run alembic upgrade head
uv run newsletter sources:seed
```

Required env vars (see `.env.example`):
`ANTHROPIC_API_KEY`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`,
`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`,
`NEWSLETTER_RECIPIENTS`, `DB_URL` (default `sqlite:///data/newsletter.db`).

Optional env vars:
`VOYAGE_API_KEY` (semantic embeddings — Jaccard fallback if unset),
`SLACK_WEBHOOK_URL` (Slack distribution — disabled if unset),
`COMPANY_CONTEXT_DIR` (corpus RAG for scoring boost — disabled if unset).

---

## Run

| Command | What it does |
|---|---|
| `uv run newsletter sources:list` | List configured sources |
| `uv run newsletter sources:add` | Add a new source |
| `uv run newsletter sources:disable <id>` | Disable a source |
| `uv run newsletter departments seed` | Seed default departments for per-department tips |
| `uv run newsletter departments list` | List registered departments |
| `uv run newsletter collect --date today` | Fetch from all enabled sources → `RawItem` |
| `uv run newsletter process --date today` | Normalize, dedupe, AI-relevance filter, track classify → `ProcessedItem` |
| `uv run newsletter integrate --date today` | Cluster + importance score + candidate selection |
| `uv run newsletter draft --date today --track all` | Generate two-track newsletter draft |
| `uv run newsletter review --date today` | Export review file to `data/reviews/` |
| `uv run newsletter review:approve --issue ID --by NAME` | Mark issue as approved |
| `uv run newsletter send --issue ID [--dry-run]` | Send approved issue via SMTP |
| `uv run newsletter slack --issue ID [--dry-run] [--force]` | Post approved issue to Slack as a summary card |
| `uv run newsletter corpus index \| list \| clear \| status` | Index / inspect / clear internal company document corpus |
| `uv run newsletter run --date today --until draft` | Run end-to-end up to a step |
| `uv run newsletter stats --date today` | Step counts, token usage, cost |
| `uv run newsletter trends [--period week\|month] [--end DATE] [--top N] [--min-count N] [--save PATH]` | Period-over-period AI topic trend report (rising / cooling / new / gone) |

---

## Test

```bash
uv run pytest                       # all
uv run pytest tests/slices/sources  # one slice
uv run pytest -k test_name -v       # one test
```

**Mock rules:**
- HTTP → `respx`
- LLM → stub `anthropic` responses
- Time → `freezegun.freeze_time`
- No real external calls in tests. Network-dependent tests do not belong in CI.

---

## Code style

- Format/lint: `uv run ruff format` and `uv run ruff check --fix`
- Type hints required for public functions
- `pathlib.Path` over `os.path`
- Imports ordered by ruff (stdlib → third-party → first-party)
- Docstrings only when behavior is non-obvious
- No comments that restate what the code does; only comments that explain *why* a non-obvious choice was made

---

## Architecture

Modular monolith with vertical slices. A slice owns its CLI, services, repositories, prompts, and tests.

```
src/newsletter/
├── core/             config, logging, db, llm client, prompt loader
├── models/           SQLAlchemy models shared across slices
├── slices/
│   ├── sources/         Source Registry CRUD + CLI
│   ├── collection/      Adapters: naver, rss, youtube → RawItem
│   ├── processing/      Normalize, dedupe, relevance, track classify
│   ├── integration/     Scoring, clustering, candidate selection
│   ├── newsletter/      Two-track section writers + assembler
│   ├── review/          Review file export + approve/reject
│   ├── distribution/    Email template + SMTP send
│   ├── monitoring/      Run logs, token/cost stats
│   ├── corpus/          사내 문서(.md/.txt)를 청크 단위로 인덱싱해 중요도 스코어링을 보강하는 슬라이스
│   └── trends/          누적 ProcessedItem 제목 키워드의 주간/월간 변화(떠오르는/식는/신규/소멸)를 비교하는 독립 리포트 슬라이스
└── cli.py             Typer root app (mounts slice sub-apps)

prompts/              All LLM prompts (NEVER inline in Python)
templates/            Jinja2 newsletter templates
migrations/           Alembic
tests/                Mirrors src/ + e2e/
data/                 SQLite, reviews, logs (gitignored)
```

### Slice rules

- A slice may import from `core/*` and `models/*`.
- A slice MUST NOT import another slice's internal modules.
- Cross-slice communication is via persisted models or public service functions only.
- One slice = one CLI sub-app, mounted in `cli.py`.
- New external integration → new module under `slices/collection/`.

### Pipeline state machine

```
collected → processed → candidate → drafted → review_required → approved → sent
```

The send code path MUST reject any state other than `approved`. There is no `--force` flag.

---

## LLM rules

- All LLM calls go through `core/llm.py`. Slices MUST NOT import `anthropic` directly.
- `claude-sonnet-4-6` for per-item processing (relevance, summarize, classify, score).
- `claude-opus-4-7` only for final newsletter writing and the editor pass.
- Default input is `title + raw_summary`. Do NOT send full article text unless the prompt explicitly requires it.
- Every prompt specifies its output format (JSON schema or strict markdown sections).
- Every LLM call is recorded to `RunLog` (tokens in/out, cost, latency, error).

---

## Prompt rules

- All prompts live in `prompts/{expert-news,practical-insight,common}/*.md`.
- Each prompt file starts with YAML frontmatter:

  ```yaml
  ---
  name: expert-importance-scorer
  model: claude-sonnet-4-6
  version: 1
  inputs: [title, summary, source_name, trust_level]
  output_schema: {"importance": "integer 1-5", "rationale": "string"}
  ---
  ```

- Code loads prompts via `newsletter.core.prompts.load_prompt("expert-news/expert-importance-scorer.md")`.
- Changing prompt behavior = bump `version` and note it in the commit message.

---

## Commits & PRs

- Conventional Commits with slice scope:
  - `feat(sources): add Source Registry CRUD`
  - `feat(collection): add Naver adapter`
  - `fix(processing): handle empty raw_summary`
  - `chore: bootstrap project`
  - `docs: update AGENTS.md`
  - `test(integration): add clustering edge cases`
- One slice or one responsibility per commit.
- Each task in the implementation plan ends with a commit.
- Never `--no-verify` unless the user explicitly asks.
- Never amend already-pushed commits without explicit instruction.

---

## Security & safety

- `.env` is gitignored. Only `.env.example` ships.
- Gmail uses an **app password**, never the user's real password.
- Never log full prompt inputs that may contain PII or company-confidential text. Log token counts and prompt names instead.
- The send code path MUST refuse to send any newsletter whose status != `approved`.
- All external network calls set an explicit timeout (default 30s).
- API keys are never hardcoded in source files.

---

## Out of scope (MVP / Phase 1)

These are deliberately excluded. Do not add them without a plan revision:

- Automatic sending without human approval
- Personalized newsletters per recipient
- Department-specific routing
- Embedding-based dedup (Phase 2 candidate)
- GraphRAG / Knowledge Graph
- Crawling beyond official APIs / RSS
- Paid news APIs
- Microsoft Teams distribution (Phase 2+ candidate; Slack is implemented)

---

## Reference

- Spec: [`plan/ai_newsletter_service_plan.md`](plan/ai_newsletter_service_plan.md) — sole source of truth for product behavior.
- Approved implementation plan: `C:\Users\user\.claude\plans\wondrous-cooking-quill.md`.
- Claude Code agent guide: [`CLAUDE.md`](CLAUDE.md).
