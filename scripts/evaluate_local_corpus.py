from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.evaluation.evaluator import evaluate_retrieval, evaluate_retrieval_cases
from backend.app.evaluation.workflow_evaluator import evaluate_core_workflow
from backend.app.models import EvaluationCase, ManualPage
from backend.app.retrieval.chunking import chunk_pages
from backend.app.retrieval.hybrid_search import HybridIndex
from backend.app.retrieval.pdf_processor import extract_pdf_pages, text_extraction_quality


MANUAL_DIR = ROOT / "data" / "user manual"
BENCHMARK_PATH = ROOT / "data" / "evaluation" / "multi_manual_benchmark.json"
REPORT_PATH = ROOT / "data" / "evaluation" / "latest_retrieval_report.json"
FALLBACK_MANUALS = [
    "Glamour.pdf",
    "Pulsar N160_Single Seat.pdf",
    "TVS sport.pdf",
    "splendor.pdf",
]


def load_cases() -> list[EvaluationCase]:
    payload = json.loads(BENCHMARK_PATH.read_text())
    return [EvaluationCase.model_validate(item) for item in payload]


def manuals_required_by(cases: list[EvaluationCase]) -> list[str]:
    required = {
        document_name
        for case in cases
        for document_name in case.expected_document_names
    }
    return sorted(required) or FALLBACK_MANUALS


def load_pages(manuals: list[str]) -> tuple[list[ManualPage], list[dict]]:
    pages: list[ManualPage] = []
    quality_rows = []
    for name in manuals:
        pdf_path = MANUAL_DIR / name
        if not pdf_path.exists():
            raise FileNotFoundError(f"Benchmark manual not found: {pdf_path}")
        extracted = extract_pdf_pages(name, pdf_path.read_bytes())
        pages.extend(extracted)
        non_empty_pages = sum(1 for page in extracted if page.text.strip())
        quality_rows.append(
            {
                "document_name": name,
                "pages": len(extracted),
                "non_empty_pages": non_empty_pages,
                "text_extraction_quality": round(text_extraction_quality(extracted), 4),
                "characters": sum(len(page.text) for page in extracted),
            }
        )
    return pages, quality_rows


def category_counts(cases: list[EvaluationCase]) -> dict[str, int]:
    return dict(sorted(Counter(case.category for case in cases).items()))


def status_counts(cases: list[EvaluationCase]) -> dict[str, int]:
    return dict(sorted(Counter(case.expected_status for case in cases).items()))


def main() -> None:
    cases = load_cases()
    manuals = manuals_required_by(cases)
    pages, extraction_quality = load_pages(manuals)
    chunks = chunk_pages(pages)
    index = HybridIndex.from_chunks(chunks)

    metrics = evaluate_retrieval(cases, index.search)
    case_results = evaluate_retrieval_cases(cases, index.search)
    workflow = evaluate_core_workflow(cases, index.search)
    report = {
        "manuals": manuals,
        "pages": len(pages),
        "chunks": len(chunks),
        "benchmark_summary": {
            "case_count": len(cases),
            "expected_status_counts": status_counts(cases),
            "category_counts": category_counts(cases),
        },
        "extraction_quality": extraction_quality,
        "metrics": metrics,
        "case_results": case_results,
        "workflow": workflow,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f"\nReport written to {REPORT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
