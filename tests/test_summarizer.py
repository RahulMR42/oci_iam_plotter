"""Tests for compact LLM context and offline summaries."""

from oci_iam_plotter.analysis import policy_analysis
from oci_iam_plotter.summarizer import DEFAULT_MODEL_ID, deterministic_summary, summary_context


def test_summary_context_is_compact_and_structured(snapshot) -> None:
    analysis = policy_analysis(snapshot, "user-1")
    context = summary_context(analysis)
    assert context["user"] == {"id": "user-1", "name": "alice"}
    assert "metadata" not in context["user"]
    assert context["policy_exposure"][0]["verb"] == "read"


def test_deterministic_summary_disclaims_authorization(snapshot) -> None:
    text = deterministic_summary(policy_analysis(snapshot, "user-1"))
    assert "not a final OCI authorization decision" in text


def test_default_model_is_openai_or_xai_not_cohere() -> None:
    assert DEFAULT_MODEL_ID.startswith(("openai.", "xai."))
    assert "cohere" not in DEFAULT_MODEL_ID
