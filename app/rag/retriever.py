"""Lexical retrieval, with an optional Chroma index when a model key is set."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from app.config import Settings
from app.rag.corpus import CorpusDocument

MIN_SCORE = 0.15
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "be",
    "between",
    "can",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "in",
    "into",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "using",
    "what",
    "whats",
    "when",
    "will",
    "with",
    "you",
    "your",
}


@dataclass(frozen=True)
class Hit:
    id: str
    title: str
    url: str
    text: str
    score: float


class BM25Retriever:
    def __init__(self, documents: list[CorpusDocument]) -> None:
        self.documents = documents
        tokenized = [tokenize(f"{doc.title}\n{doc.body}") for doc in documents]
        self._bm25 = BM25Okapi(tokenized) if tokenized else None

    def search(self, query: str, k: int = 3) -> list[Hit]:
        tokens = tokenize(query)
        if not tokens or self._bm25 is None:
            return []
        raw_scores = self._bm25.get_scores(tokens)
        hits: list[Hit] = []
        for document, raw in zip(self.documents, raw_scores):
            value = float(raw)
            score = value / (value + 1.0) if value > 0 else 0.0
            if score <= 0:
                continue
            hits.append(
                Hit(
                    id=document.id,
                    title=document.title,
                    url=document.url,
                    text=document.body,
                    score=score,
                )
            )
        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[:k]


class ChromaRetriever:
    """Used only when OPENAI_API_KEY is set and chromadb imports."""

    def __init__(self, documents: list[CorpusDocument], settings: Settings) -> None:
        import chromadb
        from openai import OpenAI

        kwargs: dict[str, str] = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        self._embedder = OpenAI(**kwargs)
        self._model = "text-embedding-3-small"
        settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(settings.chroma_dir))
        self._collection = client.get_or_create_collection("getnet-corpus")
        self._documents = {document.id: document for document in documents}
        ids = [document.id for document in documents]
        embeddings = self._embed([f"{document.title}\n{document.body}" for document in documents])
        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=[document.body for document in documents],
            metadatas=[{"title": document.title, "url": document.url} for document in documents],
        )

    def search(self, query: str, k: int = 3) -> list[Hit]:
        result = self._collection.query(query_embeddings=self._embed([query]), n_results=k)
        hits: list[Hit] = []
        ids = (result.get("ids") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        for doc_id, distance in zip(ids, distances):
            document = self._documents.get(doc_id)
            if document is None:
                continue
            score = 1.0 / (1.0 + float(distance))
            hits.append(
                Hit(
                    id=document.id,
                    title=document.title,
                    url=document.url,
                    text=document.body,
                    score=score,
                )
            )
        return hits

    def _embed(self, texts: list[str]) -> list[list[float]]:
        response = self._embedder.embeddings.create(model=self._model, input=texts)
        return [item.embedding for item in response.data]


def build_retriever(documents: list[CorpusDocument], settings: Settings) -> BM25Retriever | ChromaRetriever:
    lexical = BM25Retriever(documents)
    if not settings.openai_api_key:
        return lexical
    try:
        return ChromaRetriever(documents, settings)
    except Exception:
        return lexical


def tokenize(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", text)
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    tokens = re.findall(r"[a-z0-9]+", without_marks.lower())
    return [token for token in tokens if token not in _STOPWORDS and len(token) > 1]
