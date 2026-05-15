"""Processing slice — normalize, dedupe, AI-relevance, track classify."""

from newsletter.slices.processing.cli import app as cli_app
from newsletter.slices.processing.service import ProcessingReport, process

__all__ = ["ProcessingReport", "cli_app", "process"]
