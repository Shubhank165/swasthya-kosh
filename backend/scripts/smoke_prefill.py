"""Find a working PREFILL_MODEL_ID and prove the prefill path end to end.

Temporary diagnostic — delete once prefill is confirmed working.

    docker compose run --rm --entrypoint python api backend/scripts/smoke_prefill.py

`VertexPrefillProvider.suggest` deliberately swallows every exception and
returns None, which is right for production and useless for setup. This calls
the client directly so the real error is visible, then runs one true suggest().
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.adapters.llm.vertex import VertexPrefillProvider  # noqa: E402
from app.core.config import Settings  # noqa: E402

CANDIDATES = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-2.5-flash",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash",
]

QUESTIONS = [
    {
        "field_id": "fever_present",
        "answer_type": "yes_no_unknown",
        "prompt": "Do you have a fever?",
    },
    {
        "field_id": "pain_site",
        "answer_type": "single_choice",
        "prompt": "Where is the pain?",
        "options": ["head", "chest", "upper_abdomen", "lower_abdomen", "back"],
    },
    {
        "field_id": "symptom_duration",
        "answer_type": "duration",
        "prompt": "How long has this been going on?",
    },
]

FREE_TEXT = (
    "Mujhe teen din se bukhar hai aur pet ke upar wale hisse mein jalan ho rahi hai, "
    "khaas kar khane ke baad."
)


def banner(msg: str) -> None:
    print("\n" + "=" * 70)
    print(msg)
    print("=" * 70)


async def main() -> int:
    settings = Settings()

    banner("CONFIG")
    print(f"  project : {settings.vertex_project}")
    print(f"  region  : {settings.vertex_region}")
    print(f"  zdr     : {settings.vertex_zdr_enabled}")
    print(f"  provider: {settings.prefill_provider}")
    print(f"  model   : {settings.prefill_model_id or '(empty)'}")

    if not settings.vertex_project:
        print("\nVERTEX_PROJECT is empty. Fix .env first.")
        return 1

    # --- what does this project actually offer? ---------------------------
    banner("MODELS VISIBLE TO THIS PROJECT")
    try:
        from google import genai

        client = genai.Client(
            vertexai=True,
            project=settings.vertex_project,
            location=settings.vertex_region,
        )
        names = []
        for m in client.models.list():
            name = getattr(m, "name", "") or ""
            if "gemini" in name.lower():
                names.append(name)
        if names:
            for n in sorted(set(names)):
                print(f"  {n}")
        else:
            print("  (list returned nothing usable — relying on the probe below)")
    except Exception as exc:  # noqa: BLE001
        print(f"  could not list models: {type(exc).__name__}: {exc}")

    # --- probe candidates -------------------------------------------------
    banner("PROBING MODEL IDS")
    working: list[str] = []
    tried = ([settings.prefill_model_id] if settings.prefill_model_id else []) + CANDIDATES
    seen = set()
    for model_id in tried:
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        try:
            resp = await client.aio.models.generate_content(
                model=model_id, contents="Reply with the single word: ok"
            )
            print(f"  OK       {model_id}  -> {(resp.text or '').strip()[:40]}")
            working.append(model_id)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).replace("\n", " ")[:150]
            print(f"  FAILED   {model_id}  -> {type(exc).__name__}: {msg}")

    if not working:
        banner("RESULT: no model worked")
        print("Check the errors above. A 403 usually means the service account is")
        print("missing roles/aiplatform.user; a 404 means the model id is wrong or")
        print("not offered in this region.")
        return 1

    # --- real prefill call ------------------------------------------------
    chosen = settings.prefill_model_id if settings.prefill_model_id in working else working[0]
    banner(f"REAL PREFILL CALL using {chosen}")
    print(f"patient said: {FREE_TEXT}\n")

    provider = VertexPrefillProvider(
        Settings(**{**settings.model_dump(), "prefill_model_id": chosen})
    )
    result = await provider.suggest(free_text=FREE_TEXT, questions=QUESTIONS)
    if result is None:
        print("suggest() returned None — the call failed inside the provider.")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))

    banner("DONE")
    print(f"Put this in .env:\n\n    PREFILL_MODEL_ID={chosen}\n")
    if len(working) > 1:
        print(f"Also worked: {', '.join(m for m in working if m != chosen)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
