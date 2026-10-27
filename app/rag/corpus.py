"""Load the curated Getnet corpus."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CorpusDocument:
    id: str
    title: str
    url: str
    body: str


def load_corpus(path: Path) -> list[CorpusDocument]:
    documents: list[CorpusDocument] = []
    for file in sorted(path.glob("*.md")):
        title, url, body = _split_front_matter(file.read_text(encoding="utf-8"))
        documents.append(CorpusDocument(id=file.stem, title=title, url=url, body=body))
    return documents


def _split_front_matter(text: str) -> tuple[str, str, str]:
    if not text.startswith("---"):
        return "Untitled", "", text.strip()
    end = text.find("\n---", 3)
    if end < 0:
        return "Untitled", "", text.strip()
    header = text[3:end]
    body = text[end + 4 :].strip()
    title = ""
    url = ""
    for line in header.splitlines():
        if line.startswith("title:"):
            title = line.split(":", 1)[1].strip()
        elif line.startswith("url:"):
            url = line.split(":", 1)[1].strip()
    return title or "Untitled", url, body
