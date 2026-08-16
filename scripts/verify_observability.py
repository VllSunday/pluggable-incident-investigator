from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

from langsmith import Client
from langsmith.wrappers import wrap_openai
from openai import AsyncOpenAI

from incident_investigator.settings import (
    Settings,
    configure_langsmith_environment,
)


async def verify() -> None:
    settings = Settings()
    configure_langsmith_environment(settings)
    if not settings.langsmith_tracing:
        raise RuntimeError("Set LANGSMITH_TRACING=true before running this check")
    if settings.openai_api_key is None:
        raise RuntimeError("Set INVESTIGATOR_OPENAI_API_KEY before running this check")

    started_at = datetime.now(UTC) - timedelta(seconds=2)
    raw_client = AsyncOpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        timeout=45,
        max_retries=2,
    )
    client = wrap_openai(raw_client)
    try:
        response = await client.responses.create(
            model=settings.openai_model,
            input="Reply with exactly: observability-ok",
            max_output_tokens=64,
        )
    finally:
        await raw_client.close()

    traced_run = None
    langsmith = Client()
    project = langsmith.read_project(project_name=settings.langsmith_project)
    for _ in range(10):
        runs = langsmith.runs.query(
            project_ids=[str(project.id)],
            run_type="llm",
            min_start_time=started_at,
            page_size=20,
        )
        async for run in runs:
            traced_run = run
            break
        if traced_run is not None:
            break
        await asyncio.sleep(1)
    if traced_run is None:
        raise RuntimeError("The LLM call succeeded but no LangSmith LLM span was found")

    usage = response.usage
    print(
        json.dumps(
            {
                "openai_call": "ok",
                "langsmith_llm_span": "ok",
                "project": settings.langsmith_project,
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
                "run_id": str(traced_run.id),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(verify())
