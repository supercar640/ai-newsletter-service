"""SourceCreate / SourceUpdate validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from newsletter.slices.sources.schemas import SourceCreate, SourceUpdate


def _minimal_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "source_id": "naver-ai",
        "name": "Naver AI",
        "type": "NAVER_API",
        "content_track": "expert_news",
        "endpoint": "https://example.com",
    }
    base.update(overrides)
    return base


def test_source_create_with_defaults() -> None:
    payload = SourceCreate(**_minimal_payload())
    assert payload.priority == "medium"
    assert payload.trust_level == "media"
    assert payload.fetch_interval == "daily"
    assert payload.enabled is True
    assert payload.auth_required is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("type", "INVALID"),
        ("content_track", "no_such_track"),
        ("priority", "urgent"),
        ("trust_level", "anonymous"),
        ("fetch_interval", "yearly"),
        ("audience_level", "wizard"),
    ],
)
def test_source_create_rejects_bad_enum(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        SourceCreate(**_minimal_payload(**{field: value}))


@pytest.mark.parametrize("bad_id", ["", "Bad ID", "UPPER", "with space", "-leading-dash"])
def test_source_create_rejects_invalid_id(bad_id: str) -> None:
    with pytest.raises(ValidationError):
        SourceCreate(**_minimal_payload(source_id=bad_id))


def test_source_update_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        SourceUpdate.model_validate({"bogus": "value"})


def test_source_update_all_optional() -> None:
    upd = SourceUpdate()
    assert upd.model_dump(exclude_unset=True) == {}
