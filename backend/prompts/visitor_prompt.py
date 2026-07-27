"""Visitor system prompt loader.

This module exposes a single function that loads the Visitor system prompt
from the Markdown file `visitor_instructions.md`.

The Markdown file is the single source of truth for the Visitor prompt.
The prompt is never hardcoded inside this Python module.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

# The Markdown file lives next to this module.
_PROMPT_FILE = Path(__file__).resolve().parent / "visitor_instructions.md"


@lru_cache(maxsize=1)
def build_visitor_system_prompt() -> str:
    """Build and return the Visitor system prompt.

    Loads the content of `visitor_instructions.md` and returns it as a string.
    The file is cached after the first read.

    Returns:
        The full Visitor system prompt text.

    Raises:
        FileNotFoundError: If `visitor_instructions.md` is missing.
    """
    if not _PROMPT_FILE.is_file():
        raise FileNotFoundError(
            f"Visitor instructions file not found: {_PROMPT_FILE}"
        )

    return _PROMPT_FILE.read_text(encoding="utf-8")


__all__ = ["build_visitor_system_prompt"]