from backend.app.evaluation.workflow_evaluator import evaluate_core_workflow
from backend.app.models import Chunk, EvaluationCase, SearchHit


def test_workflow_evaluator_handles_unsupported_without_search() -> None:
    case = EvaluationCase(
        id="unsupported",
        query="What is the resale value of this bike?",
        expected_status="low_confidence",
        category="unsupported",
    )
    report = evaluate_core_workflow([case], lambda query, top_k=5: [])
    assert report["workflow_status_accuracy"] == 1.0


def test_workflow_evaluator_handles_success() -> None:
    case = EvaluationCase(
        id="supported",
        query="For Pulsar N160, what is the spark plug gap?",
        expected_status="success",
        category="supported_exact",
    )
    chunk = Chunk(
        chunk_id="1",
        document_name="manual.pdf",
        page_start=1,
        page_end=1,
        section_title="Specs",
        text="spark plug gap 0.8 ~ 0.9 mm",
    )
    report = evaluate_core_workflow(
        [case],
        lambda query, top_k=5: [
            SearchHit(chunk=chunk, lexical_score=1, semantic_score=1, combined_score=1)
        ],
    )
    assert report["workflow_status_accuracy"] == 1.0
