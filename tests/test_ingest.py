from app.config import Settings
from app.rag.corpus import load_corpus
from app.rag.ingest import SPECIFIED_URLS, extract_page

SAMPLE = """
<html><head><title>Getnet - Home</title><style>.x{color:red}</style></head>
<body><script>var secret = 1;</script><h1>The Leading AI Payments Company</h1>
<p>In-person Payments and Online Payments.</p></body></html>
"""


def test_extract_page_keeps_visible_text() -> None:
    title, body = extract_page(SAMPLE)
    assert title == "Getnet - Home"
    assert "Leading AI Payments Company" in body
    assert "In-person Payments" in body
    assert "secret" not in body
    assert "color:red" not in body


def test_corpus_contains_both_specified_urls() -> None:
    documents = load_corpus(Settings.from_env().corpus_dir)
    by_url = {document.url: document for document in documents}
    assert set(SPECIFIED_URLS).issubset(by_url)
    for url in SPECIFIED_URLS:
        document = by_url[url]
        assert len(document.body) > 500
        assert "Payments" in document.body
