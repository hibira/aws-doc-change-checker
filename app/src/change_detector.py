"""Change Detector module: Detect changes by comparing content hashes stored in DynamoDB."""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import boto3

logger = logging.getLogger(__name__)


def get_dynamodb_table():
    """Get the DynamoDB table resource."""
    table_name = os.environ["DYNAMODB_TABLE"]
    region = os.environ.get("AWS_REGION_NAME", "us-east-1")
    dynamodb = boto3.resource("dynamodb", region_name=region)
    return dynamodb.Table(table_name)


def detect_changes(pages: list[dict]) -> list[dict]:
    """Compare each page's content hash with the stored value in DynamoDB and return changed pages.

    Args:
        pages: [{"url": str, "title": str, "content": str}, ...]

    Returns:
        list of dict: [{"url": str, "title": str, "content": str, "previous_content": str | None}, ...]
    """
    table = get_dynamodb_table()
    changed_pages = []

    for page in pages:
        url = page["url"]
        content = page["content"]
        content_hash = _compute_hash(content)

        # Retrieve the previous hash from DynamoDB
        previous_record = _get_previous_record(table, url)

        if previous_record is None:
            # New page: first-time record
            logger.info(f"New page detected: {url}")
            _save_record(table, url, content_hash, content, page["title"])
            changed_pages.append({**page, "previous_content": None, "is_new": True})
        elif previous_record.get("content_hash") != content_hash:
            # Change detected
            logger.info(f"Change detected: {url}")
            previous_content = previous_record.get("content", "")
            _save_record(table, url, content_hash, content, page["title"])
            changed_pages.append({**page, "previous_content": previous_content, "is_new": False})
        else:
            # No change
            logger.debug(f"No change: {url}")
            _update_last_checked(table, url)

    return changed_pages


def _compute_hash(content: str) -> str:
    """Compute the SHA-256 hash of the content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _get_previous_record(table, url: str) -> Optional[dict]:
    """Retrieve the previous record from DynamoDB."""
    try:
        response = table.get_item(Key={"url": url})
        return response.get("Item")
    except Exception as e:
        logger.error(f"Failed to get record for {url}: {e}")
        return None


def _save_record(table, url: str, content_hash: str, content: str, title: str):
    """Save a record to DynamoDB."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        table.put_item(
            Item={
                "url": url,
                "content_hash": content_hash,
                "content": content,
                "title": title,
                "last_checked": now,
                "last_changed": now,
            }
        )
    except Exception as e:
        logger.error(f"Failed to save record for {url}: {e}")


def _update_last_checked(table, url: str):
    """Update only the last_checked timestamp."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        table.update_item(
            Key={"url": url},
            UpdateExpression="SET last_checked = :ts",
            ExpressionAttributeValues={":ts": now},
        )
    except Exception as e:
        logger.error(f"Failed to update last_checked for {url}: {e}")
