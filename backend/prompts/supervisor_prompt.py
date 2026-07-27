"""Supervisor system prompt loader.

This module exposes a single function that loads the Supervisor system prompt
from the Markdown file `supervisor_instructions.md`.

The Markdown file is the single source of truth for the Supervisor prompt.
The prompt is never hardcoded inside this Python module.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

# The Markdown file lives next to this module.
_PROMPT_FILE = Path(__file__).resolve().parent / "supervisor_instructions.md"


@lru_cache(maxsize=1)
def build_supervisor_system_prompt() -> str:
    """Build and return the Supervisor system prompt.

    Loads the content of `supervisor_instructions.md` and returns it as a string.
    The file is cached after the first read.

    Returns:
        The full Supervisor system prompt text.

    Raises:
        FileNotFoundError: If `supervisor_instructions.md` is missing.
    """
    if not _PROMPT_FILE.is_file():
        raise FileNotFoundError(
            f"Supervisor instructions file not found: {_PROMPT_FILE}"
        )

    return _PROMPT_FILE.read_text(encoding="utf-8")


__all__ = ["build_supervisor_system_prompt"]