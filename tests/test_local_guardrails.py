from backend.app.reasoning.local_guardrails import local_guardrail_decision


def test_modification_query_is_refused_before_retrieval() -> None:
    decision = local_guardrail_decision("How do I modify my bike to make it faster?")
    assert decision.decision == "low_confidence"


def test_generic_noise_needs_clarification() -> None:
    decision = local_guardrail_decision("My bike is making noise.")
    assert decision.decision == "clarification_needed"


def test_specific_supported_query_continues() -> None:
    decision = local_guardrail_decision("For Pulsar N160, what is the spark plug gap?")
    assert decision.decision == "continue"

