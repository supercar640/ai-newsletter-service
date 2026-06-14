"""Tests for the expert-track section pipeline (Iteration 5).

LLM calls are stubbed — these tests verify:

- the cluster summarizer renders the right prompt and parses the
  returned JSON into a :class:`ClusterSummary`
- malformed JSON / missing fields fall back gracefully
- the section writer renders the writer prompt with opus and returns
  the markdown verbatim
- the empty-cluster path short-circuits without spending LLM calls
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from newsletter.core.llm import LLMError, LLMResponse
from newsletter.slices.newsletter.expert import (
    ClusterBrief,
    ClusterMember,
    ClusterSummary,
    build_expert_section,
    summarize_cluster,
    summarize_clusters,
    write_expert_section,
)


def _members(*titles: str) -> tuple[ClusterMember, ...]:
    return tuple(
        ClusterMember(
            id=i,
            title=t,
            url=f"https://example.com/{i}",
            summary=f"summary of {t}",
            source_name=f"Source{i}",
        )
        for i, t in enumerate(titles, 1)
    )


# ---------------------------------------------------------------------------
# Stub LLM helpers
# ---------------------------------------------------------------------------


@dataclass
class _StubLLM:
    """Records calls and returns canned responses based on prompt model."""

    json_response: dict | None = None
    text_response: str = ""
    raise_on: str | None = None  # 'json' or 'text' to force failure
    json_calls: list[tuple[str, str]] = None  # (body, model)
    text_calls: list[tuple[str, str]] = None

    def __post_init__(self) -> None:
        self.json_calls = []
        self.text_calls = []

    def complete_json(
        self,
        body,  # type: ignore[no-untyped-def]
        *,
        tier=None,
        max_tokens=None,
        system=None,
        temperature=None,
    ):
        self.json_calls.append((body, tier))
        if self.raise_on == "json":
            raise LLMError("stub failure")
        return self.json_response, LLMResponse(
            text=json.dumps(self.json_response or {}),
            model=tier or "stub",
            input_tokens=0,
            output_tokens=0,
        )

    def complete(
        self,
        body,  # type: ignore[no-untyped-def]
        *,
        tier=None,
        max_tokens=None,
        system=None,
        temperature=None,
    ):
        self.text_calls.append((body, tier))
        if self.raise_on == "text":
            raise LLMError("stub failure")
        return LLMResponse(
            text=self.text_response,
            model=tier or "stub",
            input_tokens=0,
            output_tokens=0,
        )

    def complete_prompt(self, prompt, values, **kwargs):  # type: ignore[no-untyped-def]
        body = prompt.render(**values)
        return self.complete(body, tier=prompt.tier, **kwargs)


# ---------------------------------------------------------------------------
# summarize_cluster
# ---------------------------------------------------------------------------


class TestSummarizeCluster:
    def _payload(self) -> dict:
        return {
            "title": "OpenAI GPT-5 출시",
            "summary": "OpenAI가 새 플래그십 모델 GPT-5를 공개했다. 추론 성능이 크게 향상되었다.",
            "why_it_matters": "프런티어 모델 경쟁의 새 기준점이 된다.",
            "company_perspective": "기존 GPT-4 통합을 GPT-5로 마이그레이션 검토가 필요하다.",
            "sources": [
                {"title": "GPT-5 launches", "url": "https://example.com/1", "name": "Source1"},
            ],
        }

    def test_returns_cluster_summary(self) -> None:
        llm = _StubLLM(json_response=self._payload())
        brief = ClusterBrief(
            cluster_id="cA",
            score=0.92,
            members=_members("OpenAI launches GPT-5"),
        )
        summary = summarize_cluster(brief, llm=llm)
        assert isinstance(summary, ClusterSummary)
        assert summary.cluster_id == "cA"
        assert summary.title == "OpenAI GPT-5 출시"
        assert "GPT-5" in summary.summary
        assert summary.why_it_matters
        assert summary.company_perspective
        assert summary.sources[0]["url"] == "https://example.com/1"

    def test_sends_to_sonnet_model(self) -> None:
        llm = _StubLLM(json_response=self._payload())
        brief = ClusterBrief(
            cluster_id="cA",
            score=0.5,
            members=_members("title"),
        )
        summarize_cluster(brief, llm=llm)
        assert llm.json_calls, "summarize_cluster must call complete_json"
        _body, tier = llm.json_calls[0]
        assert tier == "fast"

    def test_members_block_includes_every_item(self) -> None:
        llm = _StubLLM(json_response=self._payload())
        brief = ClusterBrief(
            cluster_id="cA",
            score=0.5,
            members=_members("first item", "second item", "third item"),
        )
        summarize_cluster(brief, llm=llm)
        body, _ = llm.json_calls[0]
        assert "first item" in body
        assert "second item" in body
        assert "third item" in body

    def test_returns_none_on_llm_failure(self) -> None:
        llm = _StubLLM(raise_on="json")
        brief = ClusterBrief(
            cluster_id="cA",
            score=0.5,
            members=_members("anything"),
        )
        assert summarize_cluster(brief, llm=llm) is None

    def test_returns_none_on_missing_fields(self) -> None:
        llm = _StubLLM(json_response={"summary": "only summary"})  # missing title etc.
        brief = ClusterBrief(
            cluster_id="cA",
            score=0.5,
            members=_members("x"),
        )
        assert summarize_cluster(brief, llm=llm) is None

    def test_returns_none_on_non_dict_payload(self) -> None:
        llm = _StubLLM(json_response=["unexpected"])  # type: ignore[arg-type]
        brief = ClusterBrief(
            cluster_id="cA",
            score=0.5,
            members=_members("x"),
        )
        assert summarize_cluster(brief, llm=llm) is None


# ---------------------------------------------------------------------------
# summarize_clusters
# ---------------------------------------------------------------------------


class TestSummarizeClusters:
    def test_maps_over_briefs(self) -> None:
        payload = {
            "title": "T",
            "summary": "S",
            "why_it_matters": "W",
            "company_perspective": "C",
            "sources": [],
        }
        llm = _StubLLM(json_response=payload)
        briefs = [
            ClusterBrief("c1", 0.9, _members("a")),
            ClusterBrief("c2", 0.8, _members("b")),
        ]
        out = summarize_clusters(briefs, llm=llm)
        assert len(out) == 2
        assert {s.cluster_id for s in out} == {"c1", "c2"}

    def test_skips_failed_clusters(self) -> None:
        # One brief succeeds, one fails (stub will fail because payload is invalid for one).
        # We simulate by alternating with a second stub… simpler: use exception stub.
        good_payload = {
            "title": "T",
            "summary": "S",
            "why_it_matters": "W",
            "company_perspective": "C",
            "sources": [],
        }

        class _AlternatingLLM:
            def __init__(self) -> None:
                self.n = 0

            def complete_json(self, body, **k):  # type: ignore[no-untyped-def]
                self.n += 1
                if self.n == 2:
                    raise LLMError("nope")
                return good_payload, LLMResponse(
                    text="", model="stub", input_tokens=0, output_tokens=0
                )

        llm = _AlternatingLLM()
        briefs = [
            ClusterBrief("c1", 0.9, _members("a")),
            ClusterBrief("c2", 0.8, _members("b")),
            ClusterBrief("c3", 0.7, _members("c")),
        ]
        out = summarize_clusters(briefs, llm=llm)
        ids = {s.cluster_id for s in out}
        assert "c2" not in ids
        assert ids == {"c1", "c3"}

    def test_empty_briefs_returns_empty(self) -> None:
        llm = _StubLLM(json_response={})
        assert summarize_clusters([], llm=llm) == []
        assert llm.json_calls == []


# ---------------------------------------------------------------------------
# write_expert_section
# ---------------------------------------------------------------------------


def _sum(cid: str = "cA") -> ClusterSummary:
    return ClusterSummary(
        cluster_id=cid,
        title="T",
        summary="S",
        why_it_matters="W",
        company_perspective="C",
        sources=({"title": "src", "url": "https://example.com/x", "name": "Source"},),
    )


class TestWriteExpertSection:
    def test_uses_opus_model(self) -> None:
        llm = _StubLLM(text_response="## A. ...\n\nbody")
        write_expert_section([_sum()], date="2026-05-15", llm=llm)
        assert llm.text_calls, "section writer must call complete via prompt"
        _body, tier = llm.text_calls[0]
        assert tier == "quality"

    def test_returns_markdown_from_llm(self) -> None:
        llm = _StubLLM(text_response="## A. AI 전문가용 최신 AI 뉴스\n\nbody")
        section = write_expert_section([_sum()], date="2026-05-15", llm=llm)
        assert section.markdown.startswith("## A.")
        assert section.cluster_summaries == [_sum()]

    def test_passes_cluster_summaries_to_writer(self) -> None:
        llm = _StubLLM(text_response="ok")
        write_expert_section([_sum("cA"), _sum("cB")], date="2026-05-15", llm=llm)
        body, _ = llm.text_calls[0]
        assert "cA" in body
        assert "cB" in body
        assert "2026-05-15" in body

    def test_empty_summaries_short_circuits(self) -> None:
        llm = _StubLLM(text_response="should not be used")
        section = write_expert_section([], date="2026-05-15", llm=llm)
        assert llm.text_calls == []
        # Empty section still has the spec'd headings + the date.
        assert "## A. AI 전문가용 최신 AI 뉴스" in section.markdown
        assert "이번 주 해당 내용 없음" in section.markdown
        assert section.cluster_summaries == []

    def test_writer_failure_falls_back_to_local_render(self) -> None:
        llm = _StubLLM(raise_on="text")
        section = write_expert_section([_sum()], date="2026-05-15", llm=llm)
        # We still get *some* markdown back so the pipeline can continue.
        assert "## A. AI 전문가용 최신 AI 뉴스" in section.markdown
        # The cluster's title and source URL must appear in the fallback.
        assert "T" in section.markdown
        assert "https://example.com/x" in section.markdown


# ---------------------------------------------------------------------------
# build_expert_section (full pipeline)
# ---------------------------------------------------------------------------


class TestBuildExpertSection:
    def test_full_pipeline_writes_markdown(self) -> None:
        payload = {
            "title": "T",
            "summary": "S",
            "why_it_matters": "W",
            "company_perspective": "C",
            "sources": [{"title": "src", "url": "https://example.com/1", "name": "Source1"}],
        }
        llm = _StubLLM(json_response=payload, text_response="## A. ok")
        briefs = [ClusterBrief("c1", 0.9, _members("title"))]
        section = build_expert_section(briefs, date="2026-05-15", llm=llm)
        assert section.markdown.startswith("## A.")
        assert len(section.cluster_summaries) == 1

    def test_no_briefs_short_circuits(self) -> None:
        llm = _StubLLM(json_response={}, text_response="x")
        section = build_expert_section([], date="2026-05-15", llm=llm)
        assert section.cluster_summaries == []
        assert llm.json_calls == []
        assert llm.text_calls == []
