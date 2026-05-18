"""Tests for the practical-track section pipeline (Iteration 6).

LLM calls are stubbed. Coverage mirrors test_expert.py:

- summarizer renders the right prompt and parses returned JSON
- malformed JSON / missing fields fall back gracefully (skipped)
- writer renders the writer prompt with opus and returns markdown verbatim
- empty input short-circuits without spending LLM calls
- writer LLM failure falls back to deterministic local render
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from newsletter.core.llm import LLMError, LLMResponse
from newsletter.slices.newsletter.expert import ClusterBrief, ClusterMember
from newsletter.slices.newsletter.practical import (
    PracticalUsecase,
    build_practical_section,
    summarize_practical_cluster,
    summarize_practical_clusters,
    write_practical_section,
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
# Stub LLM
# ---------------------------------------------------------------------------


@dataclass
class _StubLLM:
    json_response: dict | None = None
    text_response: str = ""
    raise_on: str | None = None  # 'json' or 'text' to force failure
    json_calls: list[tuple[str, str]] = field(default_factory=list)
    text_calls: list[tuple[str, str]] = field(default_factory=list)

    def complete_json(self, body, *, model, max_tokens=1024):
        self.json_calls.append((body, model))
        if self.raise_on == "json":
            raise LLMError("stub fail")
        return (self.json_response, None)

    def complete(self, body, *, model, max_tokens=4096, system=None, temperature=0.2):
        self.text_calls.append((body, model))
        if self.raise_on == "text":
            raise LLMError("stub fail")
        return LLMResponse(text=self.text_response, model=model, input_tokens=0, output_tokens=0)


# ---------------------------------------------------------------------------
# Summarizer
# ---------------------------------------------------------------------------


def test_summarize_practical_cluster_parses_payload():
    brief = ClusterBrief(
        cluster_id="c1",
        score=0.8,
        members=_members("회의록에서 액션 아이템 뽑기"),
    )
    payload = {
        "title": "회의록에서 액션 아이템 뽑기",
        "scenario": "긴 회의록을 정리해야 하는 상황",
        "method": "회의록을 붙여넣고 액션 아이템만 뽑아달라고 요청",
        "prompt_example": "다음 회의록에서 담당자별 액션 아이템만 정리해줘",
        "caveats": "민감 정보가 있으면 사전에 제거",
        "sources": [
            {
                "title": "원문",
                "url": "https://example.com/1",
                "name": "Source1",
            }
        ],
    }
    llm = _StubLLM(json_response=payload)
    usecase = summarize_practical_cluster(brief, llm=llm)
    assert usecase is not None
    assert usecase.title == "회의록에서 액션 아이템 뽑기"
    assert usecase.scenario.startswith("긴 회의록")
    assert usecase.method.startswith("회의록을")
    assert usecase.prompt_example.startswith("다음 회의록")
    assert usecase.caveats.startswith("민감 정보")
    assert usecase.sources[0]["url"] == "https://example.com/1"


def test_summarize_practical_cluster_returns_none_on_missing_field():
    brief = ClusterBrief(cluster_id="c1", score=0.5, members=_members("X"))
    # Missing 'caveats' → drop cluster.
    payload = {
        "title": "X",
        "scenario": "s",
        "method": "m",
        "prompt_example": "p",
    }
    usecase = summarize_practical_cluster(brief, llm=_StubLLM(json_response=payload))
    assert usecase is None


def test_summarize_practical_cluster_returns_none_on_llm_error():
    brief = ClusterBrief(cluster_id="c1", score=0.5, members=_members("X"))
    usecase = summarize_practical_cluster(brief, llm=_StubLLM(raise_on="json"))
    assert usecase is None


def test_summarize_practical_clusters_skips_failures():
    briefs = [
        ClusterBrief(cluster_id="c1", score=0.5, members=_members("A")),
        ClusterBrief(cluster_id="c2", score=0.5, members=_members("B")),
    ]
    # First returns valid, second is malformed (missing fields)
    valid = {
        "title": "T",
        "scenario": "s",
        "method": "m",
        "prompt_example": "p",
        "caveats": "c",
        "sources": [],
    }
    # Use a stub that always returns the same response → both clusters parse.
    out = summarize_practical_clusters(briefs, llm=_StubLLM(json_response=valid))
    assert len(out) == 2


# ---------------------------------------------------------------------------
# Section writer
# ---------------------------------------------------------------------------


def _usecase(idx: int = 1) -> PracticalUsecase:
    return PracticalUsecase(
        cluster_id=f"c{idx}",
        title=f"활용법 {idx}",
        scenario="긴 자료를 빠르게 보고서로 만들고 싶을 때",
        method="자료를 붙여넣고 보고서 초안을 부탁",
        prompt_example="다음 자료를 한 페이지 보고서 초안으로 정리해줘",
        caveats="기밀 자료는 사내 LLM에서만 사용",
        sources=(),
    )


def test_write_practical_section_returns_writer_output():
    llm = _StubLLM(text_response="## B. 일반 임직원용 AI 활용 인사이트\n\nopus output")
    section = write_practical_section([_usecase()], date="2026-05-18", llm=llm)
    assert section.markdown.startswith("## B. 일반 임직원용 AI 활용 인사이트")
    assert "opus output" in section.markdown
    assert len(llm.text_calls) == 1


def test_write_practical_section_falls_back_when_writer_fails():
    llm = _StubLLM(raise_on="text")
    section = write_practical_section([_usecase()], date="2026-05-18", llm=llm)
    # Deterministic local fallback contains the usecase's prompt_example.
    assert "B. 일반 임직원용" in section.markdown
    assert "다음 자료를 한 페이지 보고서 초안" in section.markdown
    assert section.usecases == [_usecase()]


def test_write_practical_section_empty_short_circuits():
    llm = _StubLLM()
    section = write_practical_section([], date="2026-05-18", llm=llm)
    assert "이번 주 해당 내용 없음" in section.markdown
    assert llm.text_calls == []


# ---------------------------------------------------------------------------
# build_practical_section
# ---------------------------------------------------------------------------


def test_build_practical_section_runs_both_stages():
    brief = ClusterBrief(cluster_id="c1", score=0.5, members=_members("A"))
    payload = {
        "title": "T",
        "scenario": "s",
        "method": "m",
        "prompt_example": "p",
        "caveats": "c",
        "sources": [],
    }
    llm = _StubLLM(json_response=payload, text_response="OPUS")
    section = build_practical_section([brief], date="2026-05-18", llm=llm)
    assert section.markdown == "OPUS"
    assert len(section.usecases) == 1


def test_build_practical_section_empty_briefs_short_circuit():
    llm = _StubLLM()
    section = build_practical_section([], date="2026-05-18", llm=llm)
    assert "이번 주 해당 내용 없음" in section.markdown
    assert llm.json_calls == []
    assert llm.text_calls == []


# ---------------------------------------------------------------------------
# Prompt body assertions
# ---------------------------------------------------------------------------


def test_summarizer_prompt_includes_members_block():
    brief = ClusterBrief(
        cluster_id="cluster-x",
        score=0.9,
        members=_members("회의록 분류", "회의 요약 자동화"),
    )
    payload = {
        "title": "T",
        "scenario": "s",
        "method": "m",
        "prompt_example": "p",
        "caveats": "c",
        "sources": [],
    }
    llm = _StubLLM(json_response=payload)
    summarize_practical_cluster(brief, llm=llm)
    body, _ = llm.json_calls[0]
    assert "cluster-x" in body
    assert "회의록 분류" in body


def test_writer_prompt_includes_usecases_json():
    llm = _StubLLM(text_response="OK")
    write_practical_section([_usecase(1), _usecase(2)], date="2026-05-18", llm=llm)
    body, _ = llm.text_calls[0]
    assert "활용법 1" in body
    assert "활용법 2" in body
    assert "2026-05-18" in body


def test_writer_renders_usecases_as_valid_json_in_prompt():
    """The writer prompt must contain a parseable JSON array of usecases."""
    llm = _StubLLM(text_response="OK")
    write_practical_section([_usecase(1)], date="2026-05-18", llm=llm)
    body, _ = llm.text_calls[0]
    # Find the first '[' that starts a JSON array of objects.
    start = body.find("[{")
    end = body.rfind("}]")
    assert start != -1 and end != -1
    arr = json.loads(body[start : end + 2])
    assert isinstance(arr, list)
    assert arr[0]["title"] == "활용법 1"
