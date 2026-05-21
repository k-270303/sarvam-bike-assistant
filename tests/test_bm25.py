from backend.app.retrieval.bm25 import BM25Index


def test_bm25_prefers_exact_terms() -> None:
    index = BM25Index(
        [
            "Check spark plug gap and replace the spark plug if damaged.",
            "Inspect brake pad wear before riding.",
        ]
    )
    scores = index.score("spark plug gap")
    assert scores[0] > scores[1]

