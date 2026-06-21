import json
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from app.config import get_settings


def invoke_bedrock_json(prompt: str, *, max_tokens: int = 1200) -> dict[str, Any] | None:
    text = invoke_bedrock_text(prompt, max_tokens=max_tokens)
    if not text:
        return None
    try:
        return json.loads(_extract_json(text))
    except json.JSONDecodeError:
        return None


def invoke_bedrock_text(prompt: str, *, max_tokens: int = 1200) -> str | None:
    try:
        import boto3
    except ImportError:
        return None

    settings = get_settings()
    client = boto3.client("bedrock-runtime", region_name=settings.aws_bedrock_region)
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt,
                    }
                ],
            }
        ],
    }
    try:
        response = client.invoke_model(
            modelId=settings.aws_bedrock_model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
    except (BotoCoreError, ClientError, NoCredentialsError):
        return None

    payload = json.loads(response["body"].read())
    content = payload.get("content", [])
    if content and isinstance(content[0], dict):
        return str(content[0].get("text", "")).strip()
    return None


def _extract_json(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end >= start:
        return cleaned[start : end + 1]
    return cleaned
