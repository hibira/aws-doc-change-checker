"""AWS Documentation Change Checker - Lambda Handler."""

import json
import logging
import os

from src.crawler import crawl_documentation
from src.change_detector import detect_changes
from src.summarizer import summarize_changes
from src.notifier import send_notification

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """Lambda entrypoint: crawl -> detect changes -> summarize -> notify."""
    target_url = os.environ["TARGET_URL"]
    logger.info(f"Starting documentation change check for: {target_url}")

    # 1. Retrieve all page URLs from the documentation menu
    pages = crawl_documentation(target_url)
    logger.info(f"Found {len(pages)} pages to check")

    # 2. Detect changes for each page
    changed_pages = detect_changes(pages)
    logger.info(f"Detected {len(changed_pages)} changed pages")

    if not changed_pages:
        logger.info("No changes detected. Done.")
        return {
            "statusCode": 200,
            "body": json.dumps({"message": "No changes detected", "pages_checked": len(pages)}),
        }

    # 3. Summarize the changes
    summary = summarize_changes(changed_pages)
    logger.info("Summary generated")

    # 4. Send notification
    send_notification(summary, changed_pages)
    logger.info("Notification sent")

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": "Changes detected and notified",
                "pages_checked": len(pages),
                "pages_changed": len(changed_pages),
            }
        ),
    }
