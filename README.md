# AI Newsletter Service

Internal AI intelligence newsletter automation. Collects AI news / RSS / YouTube,
classifies into two tracks (expert news / practical insight), drafts with LLMs,
requires human review, then emails.

## Quick start

```powershell
uv sync
copy .env.example .env       # fill in keys
uv run alembic upgrade head
uv run newsletter --help
```

## Documents

- Spec (source of truth): [`plan/ai_newsletter_service_plan.md`](plan/ai_newsletter_service_plan.md)
- Agent guide (baseline): [`AGENTS.md`](AGENTS.md)
- Agent guide (Claude Code): [`CLAUDE.md`](CLAUDE.md)
