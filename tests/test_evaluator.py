from backend.app.evaluation.evaluator import evaluate_retrieval
from backend.app.models import Chunk, EvaluationCase, SearchHit


def test_evaluator_tracks_terms_and_document_hits() -> None:
    case = EvaluationCase(
        id="case",
        query="spark plug",
        expected_terms=["spark plug gap"],
        expected_document_names=["manual.pdf"],
        expected_status="success",
    )
    chunk = Chunk(
        chunk_id="1",
        document_name="manual.pdf",
        page_start=1,
        page_end=1,
        section_title="Specs",
        text="Spark plug gap 0.8 mm",
    )

    metrics = evaluate_retrieval(
        [case],
        lambda query, top_k=5: [
            SearchHit(
                chunk=chunk,
                lexical_score=1.0,
                semantic_score=1.0,
                combined_score=1.0,
            )
        ],
    )
    assert metrics["retrieval_accuracy_at_3"] == 1.0
    assert metrics["retrieval_accuracy_at_5"] == 1.0
    assert metrics["document_accuracy_at_5"] == 1.0
