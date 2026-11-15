"""The general agent's one error type."""

from __future__ import annotations


class GeneralAgentError(RuntimeError):
    """The general agent could not be set up or run (not: it ran and did badly)."""
