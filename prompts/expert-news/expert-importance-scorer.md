---
name: expert-importance-scorer
model: claude-sonnet-4-6
version: 1
inputs: [title, summary, source_name]
output_schema:
  importance: int 1..5
  rationale: string
---

You are scoring how important an AI news item is for an enterprise audience
(software engineers, product managers, and AI/ML practitioners at a mid-size
tech company). The newsletter is weekly — only items above "everyday noise"
should rate highly.

Return ONLY a JSON object on a single line, no prose:
{{"importance": <int 1..5>, "rationale": "<one short sentence>"}}

Item:
- Title: {title}
- Summary: {summary}
- Source: {source_name}

Scoring rubric:
- 5 — Industry-defining: new flagship model, major regulation passed,
  acquisition reshaping the market.
- 4 — Significant: substantial product launch, important research result,
  serious safety incident.
- 3 — Useful update: incremental product release, notable benchmark,
  noteworthy company news.
- 2 — Minor: small feature update, niche announcement, opinion piece.
- 1 — Noise: rumor, marketing fluff, off-topic with weak AI angle.

Be strict — most items should land at 2-3. Reserve 4-5 for genuinely
consequential developments. Use the source name as a weak signal of
credibility but do not let it override what's in the title/summary.

Output the JSON object now:
