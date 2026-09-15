import asyncio

from medikiosk.config import get_settings
from medikiosk.providers.openai_provider import OpenAIClinicalExtractor


async def main() -> None:
    settings = get_settings()
    if not settings.openai_api_key:
        raise SystemExit("OPENAI_API_KEY is not set")
    extractor = OpenAIClinicalExtractor(settings.openai_api_key, settings.openai_model)
    result = await extractor.extract(
        "I have had abdominal pain for three days and vomited twice. "
        "I do not know how severe it is."
    )
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())

