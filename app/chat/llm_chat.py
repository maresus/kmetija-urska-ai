"""
Direct LLM chat - Kmetija Urška AI.
"""
from __future__ import annotations

import os
from pathlib import Path
from openai import OpenAI

from app.rag.search import get_context


_SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "system.txt"
_DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


def _load_system_prompt() -> str:
    if _SYSTEM_PROMPT_PATH.exists():
        return _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    return "Si pomočnik Kmetije Urška."


def chat(
    message: str,
    history: list[dict[str, str]] | None = None,
    client: OpenAI | None = None,
    model: str | None = None,
) -> dict[str, str]:
    if model is None:
        model = _DEFAULT_MODEL

    if client is None:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    rag_context = get_context(message, top_k=3)

    system_prompt = _load_system_prompt()

    # Inject current date/day
    from datetime import datetime
    _DAYS_SL = ["ponedeljek", "torek", "sreda", "četrtek", "petek", "sobota", "nedelja"]
    now = datetime.now()
    today_day = _DAYS_SL[now.weekday()]
    tomorrow_day = _DAYS_SL[(now.weekday() + 1) % 7]
    system_prompt += (
        f"\n\n## Trenutni datum\n"
        f"Danes je {today_day}, {now.strftime('%-d. %-m. %Y')}. "
        f"Jutri je {tomorrow_day}. "
        f"Vikend je ta {_DAYS_SL[5]} in {_DAYS_SL[6]}."
    )

    if rag_context:
        system_prompt += f"\n\n## Dodatni kontekst iz baze znanja:\n{rag_context}"

    messages = [{"role": "system", "content": system_prompt}]

    if history:
        for msg in history[-6:]:
            messages.append(msg)

    messages.append({"role": "user", "content": message})

    response = client.responses.create(
        model=model,
        input=messages,
        max_output_tokens=1024,
    )

    reply = getattr(response, "output_text", None)
    if not reply:
        outputs = []
        for block in getattr(response, "output", []) or []:
            for content in getattr(block, "content", []) or []:
                text = getattr(content, "text", None)
                if text:
                    outputs.append(text)
        reply = "\n".join(outputs).strip()

    if not reply:
        reply = "Oprostite, nisem razumel vprašanja. Pokličite nas: 031 249 812"

    return {"reply": reply}
