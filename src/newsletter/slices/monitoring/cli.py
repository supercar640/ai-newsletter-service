"""``newsletter stats`` — per-step counts, tokens, cost from RunLog."""

from __future__ import annotations

from datetime import date as date_cls

import typer

from newsletter.core.db import session_scope
from newsletter.slices.monitoring.service import StepStats, aggregate_by_step

app = typer.Typer(
    name="stats",
    help="Show pipeline + LLM activity from the RunLog ledger.",
    invoke_without_command=True,
    no_args_is_help=False,
)


def _resolve_date(value: str | None) -> date_cls | None:
    if value is None:
        return None
    if value == "today":
        return date_cls.today()
    if value == "all":
        return None
    return date_cls.fromisoformat(value)


@app.callback(invoke_without_command=True)
def cmd_stats(
    date: str | None = typer.Option(
        None,
        "--date",
        help="Filter to one day (YYYY-MM-DD or 'today'). Omit / 'all' for everything.",
    ),
) -> None:
    """Print the per-step run counts, token totals, and cost in USD."""
    when = _resolve_date(date)
    with session_scope() as session:
        rows = aggregate_by_step(session, on=when)

    if not rows:
        scope = when.isoformat() if when else "any date"
        typer.echo(f"(no run logs for {scope})")
        return

    _render_table(rows, when)


def _render_table(rows: list[StepStats], when: date_cls | None) -> None:
    scope = when.isoformat() if when else "all dates"
    typer.echo(f"RunLog stats — {scope}")
    header = (
        f"{'step':22} {'runs':>5} {'ok':>4} {'fail':>5} {'items':>7} "
        f"{'tok_in':>8} {'tok_out':>8} {'cost_usd':>10}"
    )
    typer.echo(header)
    typer.echo("-" * len(header))
    total_runs = total_items = total_in = total_out = 0
    total_cost = 0.0
    total_fail = 0
    for r in rows:
        typer.echo(
            f"{r.step:22} {r.run_count:>5} {r.success_count:>4} {r.failure_count:>5} "
            f"{r.item_count:>7} {r.llm_tokens_in:>8} {r.llm_tokens_out:>8} "
            f"{r.cost_usd:>10.4f}"
        )
        total_runs += r.run_count
        total_fail += r.failure_count
        total_items += r.item_count
        total_in += r.llm_tokens_in
        total_out += r.llm_tokens_out
        total_cost += r.cost_usd
    typer.echo("-" * len(header))
    typer.echo(
        f"{'TOTAL':22} {total_runs:>5} {'-':>4} {total_fail:>5} "
        f"{total_items:>7} {total_in:>8} {total_out:>8} {total_cost:>10.4f}"
    )
