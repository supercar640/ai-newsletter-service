---
name: keyword-relevance-classifier
model: claude-sonnet-4-6
version: 1
inputs: [title, summary]
output_schema:
  is_ai_related: boolean
  confidence: float 0..1
  rationale: string
---

You are a strict classifier deciding whether a news item is about
artificial intelligence (AI, large language models, generative AI,
machine learning, AI products, AI policy, AI research, AI agents,
or AI applications).

Return ONLY a JSON object on a single line, no prose:
{{"is_ai_related": true|false, "confidence": 0.0..1.0, "rationale": "<one short sentence>"}}

Item:
- Title: {title}
- Summary: {summary}

Decision criteria:
- "true" if the item's PRIMARY subject is AI / LLMs / generative models /
  AI products / AI regulation / AI research / AI agents / AI tools.
- "false" if AI is only mentioned in passing, or the item is about
  unrelated tech (chips, devices, social media) with no AI angle.
- Lower confidence (< 0.6) when the title alone is ambiguous.

Output the JSON object now:
