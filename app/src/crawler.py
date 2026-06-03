"""Crawler module: Extract page URLs from AWS documentation via toc-contents.json."""

from __future__ import annotations

import json
import logging
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Common request headers for AWS documentation site
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AWSDocChangeChecker/1.0)",
    "Accept": "text/html,application/xhtml+xml,application/json",
    "Accept-Language": "en-US,en;q=0.9",
}

REQUEST_TIMEOUT = 30


def crawl_documentation(root_url: str) -> list:
    """Retrieve all page URLs from toc-contents.json and fetch each page's content.

    Args:
        root_url: The root URL to start crawling from.

    Returns:
        list of dict: [{"url": str, "title": str, "content": str}, ...]
    """
    logger.info(f"Crawling documentation from: {root_url}")

    # Compute the base URL (directory portion)
    base_url = root_url.rsplit("/", 1)[0] + "/"

    # Get page list from toc-contents.json
    page_urls = _extract_pages_from_toc(base_url)

    # Fallback to in-page link extraction if TOC is unavailable
    if not page_urls:
        logger.warning("TOC not available, falling back to page link extraction")
        page_urls = _extract_menu_links(root_url)
        if root_url not in page_urls:
            page_urls.insert(0, root_url)

    logger.info(f"Found {len(page_urls)} page URLs to check")

    # Fetch content for each page
    pages = []
    for url in page_urls:
        page_data = _fetch_page_content(url)
        if page_data:
            pages.append(page_data)

    return pages


def _extract_pages_from_toc(base_url: str) -> list:
    """Recursively extract all page URLs from AWS documentation toc-contents.json."""
    toc_url = base_url + "toc-contents.json"
    logger.info(f"Fetching TOC from: {toc_url}")

    try:
        response = requests.get(toc_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        toc_data = response.json()
    except (requests.RequestException, json.JSONDecodeError) as e:
        logger.warning(f"Failed to fetch TOC: {e}")
        return []

    # Recursively walk the TOC structure to build the URL list
    page_urls = []
    _walk_toc(toc_data.get("contents", []), base_url, page_urls)

    return page_urls


def _walk_toc(contents: list, base_url: str, page_urls: list):
    """Recursively walk the TOC contents array."""
    for item in contents:
        href = item.get("href", "")
        if href and href.endswith(".html"):
            absolute_url = urljoin(base_url, href)
            page_urls.append(absolute_url)

        # Recurse into child elements
        if "contents" in item:
            _walk_toc(item["contents"], base_url, page_urls)


def _extract_menu_links(root_url: str) -> list:
    """Fallback: Extract navigation URLs from in-page links."""
    try:
        response = requests.get(root_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch root page: {e}")
        return []

    soup = BeautifulSoup(response.text, "lxml")
    page_urls = []
    seen = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]

        if href.startswith("#") or href.startswith("javascript:"):
            continue

        absolute_url = urljoin(root_url, href)

        if not _is_same_doc_section(absolute_url, root_url):
            continue

        normalized = absolute_url.split("#")[0]

        if normalized not in seen and normalized.endswith(".html"):
            seen.add(normalized)
            page_urls.append(normalized)

    return page_urls


def _fetch_page_content(url: str) -> Optional[dict]:
    """Fetch the main content of a page."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch page {url}: {e}")
        return None

    soup = BeautifulSoup(response.text, "lxml")

    # Extract title
    title = _extract_title(soup)

    # Extract main content (excluding navigation, etc.)
    content = _extract_main_content(soup)

    if not content:
        logger.warning(f"No main content found for: {url}")
        return None

    return {"url": url, "title": title, "content": content}


def _extract_title(soup: BeautifulSoup) -> str:
    """Extract the page title."""
    title_selectors = [
        "h1.topictitle1",
        "#main-content h1",
        "h1",
        "title",
    ]
    for selector in title_selectors:
        element = soup.select_one(selector)
        if element:
            return element.get_text(strip=True)
    return "Untitled"


def _extract_main_content(soup: BeautifulSoup) -> str:
    """Extract the main text content of the page."""
    # Remove unnecessary elements
    for tag in soup.find_all(["script", "style", "nav", "header", "footer"]):
        tag.decompose()

    # Look for the AWS documentation main content area
    content_selectors = [
        "#main-content",
        "#main-col-body",
        "main",
        "[role='main']",
        ".awsdocs-container",
    ]

    for selector in content_selectors:
        element = soup.select_one(selector)
        if element:
            return element.get_text(separator="\n", strip=True)

    # Fallback: entire body
    body = soup.find("body")
    if body:
        return body.get_text(separator="\n", strip=True)

    return ""


def _is_same_doc_section(url: str, root_url: str) -> bool:
    """Check whether the URL belongs to the same documentation section."""
    parsed_url = urlparse(url)
    parsed_root = urlparse(root_url)

    if parsed_url.netloc != parsed_root.netloc:
        return False

    root_path_parts = parsed_root.path.rsplit("/", 1)[0]
    return parsed_url.path.startswith(root_path_parts)
