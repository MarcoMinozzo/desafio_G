"""Download the two Getnet URLs the brief names and store their page text."""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

SPECIFIED_URLS = (
    "https://www.getnet.net/",
    "https://www.getnet.net/en",
)

_SKIP_TAGS = {"script", "style", "noscript"}
_BLOCK_TAGS = {"p", "div", "li", "h1", "h2", "h3", "h4", "br", "section", "tr", "article"}


class _PageText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self._parts: list[str] = []
        self._title: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title.append(data)
        if self._skip:
            return
        text = data.strip()
        if text:
            self._parts.append(text)

    def title(self) -> str:
        value = re.sub(r"\s+", " ", "".join(self._title)).strip()
        return value or "Getnet"

    def body(self) -> str:
        text = " ".join(self._parts)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()


def document_id(url: str) -> str:
    if url.rstrip("/").endswith("/en"):
        return "getnet-en"
    return "getnet-root"


def extract_page(html: str) -> tuple[str, str]:
    parser = _PageText()
    parser.feed(html)
    parser.close()
    return parser.title(), parser.body()


def fetch_html(url: str, client: httpx.Client | None = None) -> str:
    owns_client = client is None
    http = client or httpx.Client(follow_redirects=True, timeout=30.0, headers={"User-Agent": "GetnetAssistRAG/1.0"})
    try:
        response = http.get(url)
        response.raise_for_status()
        return response.text
    finally:
        if owns_client:
            http.close()


def write_document(corpus_dir: Path, url: str, title: str, body: str) -> Path:
    if not body:
        raise ValueError(f"No text extracted from {url}")
    corpus_dir.mkdir(parents=True, exist_ok=True)
    path = corpus_dir / f"{document_id(url)}.md"
    path.write_text(f"---\ntitle: {title}\nurl: {url}\n---\n\n{body}\n", encoding="utf-8")
    return path


def ingest_specified_urls(corpus_dir: Path, client: httpx.Client | None = None) -> list[Path]:
    """Download both brief URLs and replace their corpus files with the page text."""
    written: list[Path] = []
    for url in SPECIFIED_URLS:
        html = fetch_html(url, client)
        title, body = extract_page(html)
        written.append(write_document(corpus_dir, url, title, body))
        logger.info("Ingested %s into %s (%s characters)", url, written[-1].name, len(body))
    overview = corpus_dir / "getnet-overview.md"
    if overview.exists():
        overview.unlink()
    return written


def main() -> None:
    from app.config import Settings

    logging.basicConfig(level=logging.INFO)
    ingest_specified_urls(Settings.from_env().corpus_dir)


if __name__ == "__main__":
    main()
