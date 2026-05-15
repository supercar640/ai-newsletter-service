---
name: track-classifier
model: claude-sonnet-4-6
version: 1
inputs: [title, summary]
output_schema:
  track: expert_news | practical_insight
  rationale: string
---

You sort an AI news item into one of two reader tracks:

- "expert_news"  — for AI specialists, engineers, strategists. Tech
  releases, model launches, policy/regulation, research, market moves,
  industry shifts.
- "practical_insight" — for general employees. How-to guides, prompt
  examples, productivity tips, AI tools for office work, beginner
  tutorials.

Return ONLY a JSON object on a single line:
{{"track": "expert_news"|"practical_insight", "rationale": "<one short sentence>"}}

Item:
- Title: {title}
- Summary: {summary}

Decision rules:
- A model launch announcement or research paper → "expert_news".
- A YouTube tutorial / "5 ways to use ChatGPT" type / sales-copy
  productivity article → "practical_insight".
- A policy or regulation update aimed at executives → "expert_news".
- Anything that gives a non-technical reader a concrete prompt or
  workflow → "practical_insight".

Output the JSON object now:
