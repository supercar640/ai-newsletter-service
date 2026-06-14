"""Public LLM API — provider-agnostic client + tier constants.

The import path ``newsletter.core.llm`` is preserved across the package
split; slices and tests import from here, not the submodules.
"""

from newsletter.core.llm.client import (
    LLMClient,
    LLMError,
    LLMResponse,
    _first_json_value,
)
from newsletter.core.llm.models import FAST, QUALITY

__all__ = [
    "FAST",
    "QUALITY",
    "LLMClient",
    "LLMError",
    "LLMResponse",
    "_first_json_value",
]
