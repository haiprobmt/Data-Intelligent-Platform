import json
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import LlmUsageLog


def invoke_bedrock_json(prompt: str, *, max_tokens: int = 1200, db: Session | None = None, tenant_id: str | None = None, purpose: str = "json") -> dict[str, Any] | None:
    text = invoke_bedrock_text(prompt, max_tokens=max_tokens, db=db, tenant_id=tenant_id, purpose=purpose)
    if not text:
        return None
    try:
        return json.loads(_extract_json(text))
    except json.JSONDecodeError:
        return None


def invoke_bedrock_text(prompt: str, *, max_tokens: int = 1200, db: Session | None = None, tenant_id: str | None = None, purpose: str = "text") -> str | None:
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
        text = str(content[0].get("text", "")).strip()
        log_llm_usage(db, tenant_id, settings.aws_bedrock_model_id, prompt, text, purpose)
        return text
    return None


def log_llm_usage(db: Session | None, tenant_id: str | None, model: str, prompt: str, completion: str, purpose: str) -> None:
    if db is None or tenant_id is None:
        return
    prompt_tokens = estimate_tokens(prompt)
    completion_tokens = estimate_tokens(completion)
    db.add(
        LlmUsageLog(
            tenant_id=tenant_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            estimated_cost=0.0,
            purpose=purpose,
        )
    )


def estimate_tokens(text: str) -> int:
    return max(1, round(len(text) / 4)) if text else 0


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
