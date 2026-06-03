"""Summarizer module: Summarize changes using Bedrock (Claude Sonnet 4.6)."""

import json
import logging
import os

import boto3

logger = logging.getLogger(__name__)


def get_bedrock_client():
    """Get the Bedrock Runtime client."""
    region = os.environ.get("AWS_REGION_NAME", "us-east-1")
    return boto3.client("bedrock-runtime", region_name=region)


def summarize_changes(changed_pages: list[dict]) -> str:
    """Summarize changed pages using Bedrock Claude Sonnet 4.6.

    Args:
        changed_pages: [{"url": str, "title": str, "content": str, "previous_content": str | None, "is_new": bool}, ...]

    Returns:
        str: Summary text
    """
    model_id = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
    client = get_bedrock_client()

    # Format changes for the prompt
    changes_text = _format_changes(changed_pages)

    # Generate summary via Bedrock
    prompt = _build_summary_prompt(changes_text)

    try:
        response = client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 65536,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                }
            ),
        )

        response_body = json.loads(response["body"].read())
        summary = response_body["content"][0]["text"]
        return summary

    except Exception as e:
        logger.error(f"Failed to generate summary with Bedrock: {e}")
        # Fallback: simple summary
        return _fallback_summary(changed_pages)


def _format_changes(changed_pages: list[dict]) -> str:
    """Format changed page information for the prompt."""
    parts = []

    for page in changed_pages:
        if page.get("is_new"):
            parts.append(
                f"## New page: {page['title']}\n"
                f"URL: {page['url']}\n"
                f"Content:\n{page['content']}\n"
            )
        else:
            previous = page.get('previous_content', '')
            current = page['content']
            parts.append(
                f"## Updated page: {page['title']}\n"
                f"URL: {page['url']}\n"
                f"Previous content:\n{previous}\n\n"
                f"Current content:\n{current}\n"
            )

    return "\n---\n".join(parts)


def _build_summary_prompt(changes_text: str) -> str:
    """Build the prompt for summary generation."""
    return (
        "You are an expert at analyzing AWS documentation changes.\n"
        "Summarize the following AWS documentation changes in Japanese.\n\n"
        "Summary format:\n"
        "1. Overview of changes (1-2 sentences)\n"
        "2. Changes per page (bullet points)\n"
        "3. Users or features potentially affected\n\n"
        "For new pages, summarize the main content.\n"
        "For updated pages, focus on the differences from the previous version.\n\n"
        f"Changes:\n\n{changes_text}"
    )


def _fallback_summary(changed_pages: list[dict]) -> str:
    """Fallback summary when Bedrock invocation fails."""
    lines = ["# AWS Documentation Change Report\n"]
    lines.append(f"Changed pages: {len(changed_pages)}\n")

    for page in changed_pages:
        status = "New" if page.get("is_new") else "Updated"
        lines.append(f"- [{status}] {page['title']}: {page['url']}")

    lines.append("\n* AI summary generation failed. This is a simplified report.")
    return "\n".join(lines)
