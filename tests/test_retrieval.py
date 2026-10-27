from pathlib import Path

from app.config import Settings
from app.rag.corpus import load_corpus
from app.rag.retriever import BM25Retriever

ROOT = Path(__file__).resolve().parents[1]


def retriever() -> BM25Retriever:
    settings = Settings.from_env()
    return BM25Retriever(load_corpus(settings.corpus_dir))


def test_antecipacao_hits_the_advance_document() -> None:
    hits = retriever().search("How does receivables advance (antecipação) work with Getnet?")
    assert hits
    assert hits[0].id == "antecipacao"
    assert hits[0].score >= 0.15
    assert "getnet" in hits[0].url


def test_payment_link_hits_the_whatsapp_document() -> None:
    hits = retriever().search("Can I sell through WhatsApp using the Payment Link?")
    assert hits
    assert hits[0].id == "payment-link"
    assert hits[0].score >= 0.15
    assert "getnet" in hits[0].url
