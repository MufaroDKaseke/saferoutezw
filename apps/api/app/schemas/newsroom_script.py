"""The shape the model must reply with when drafting a radio script (NUST FM newsroom).

Two plain text fields and nothing else, so an instruction hidden inside an article has no free-form channel
to travel through. Both fields are validated again here because the model is not trusted. Strict-mode
compatible, like the classification schema.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.schemas.intelligence import _Block, _strictify


class ScriptDraft(_Block):
    headline: str = Field(
        min_length=1,
        max_length=120,
        description="A short working title for the editor, under ten words. It is not read on air.",
    )
    body: str = Field(
        min_length=1,
        max_length=6000,
        description="The script exactly as the newsreader reads it: plain short sentences, no markdown, no stage directions.",
    )

    def cleaned(self) -> tuple[str, str]:
        """(headline, body) with stray whitespace tidied; paragraph breaks are kept."""
        headline = " ".join(self.headline.split())
        body = "\n\n".join(" ".join(p.split()) for p in self.body.split("\n\n") if p.strip())
        return headline, body


def build_json_schema() -> dict[str, Any]:
    return _strictify(ScriptDraft.model_json_schema())


SCRIPT_JSON_SCHEMA: dict[str, Any] = build_json_schema()
