"""On-demand OCI Generative AI summaries with a deterministic offline fallback."""

from __future__ import annotations

import json
import os
from typing import Any

from .settings import DEFAULT_MODEL_ID, DEFAULT_OPENAI_BASE_URL, DEFAULT_PROJECT_OCID, Settings

PROJECT_OCID = DEFAULT_PROJECT_OCID
OPENAI_BASE_URL = DEFAULT_OPENAI_BASE_URL


def summary_context(analysis: dict) -> dict:
    """Reduce user analysis to compact, audit-safe LLM input."""
    return {"user": {"id": analysis["user"]["id"], "name": analysis["user"]["name"]},
            "groups": [{"id": group["id"], "name": group["name"]} for group in analysis["groups"]],
            "policy_exposure": [{key: item.get(key) for key in ("policy_id", "original_text", "verb", "resource_type", "scope", "condition", "confidence")}
                                for item in analysis["applicable_policy_statements"]],
            "implied_permissions": analysis["implied_permissions"], "limitations": analysis["limitations"]}


def deterministic_summary(analysis: dict) -> str:
    """Produce a useful offline summary without contacting an LLM."""
    user = analysis["user"]["name"]
    groups = ", ".join(group["name"] for group in analysis["groups"]) or "no collected groups"
    permissions = "; ".join(analysis["implied_permissions"]) or "no matching standard group policy statements"
    return f"{user} belongs to {groups}. Policy-text inference indicates: {permissions}. This is not a final OCI authorization decision; conditions and service-specific evaluation may alter access."


class OCIReasoner:
    """Calls OCI Responses via the OpenAI SDK for requested summaries."""

    def __init__(self, project_ocid: str | None = None, model_id: str | None = None) -> None:
        settings = Settings.from_env()
        self.project_ocid = project_ocid or settings.genai_project_ocid
        self.model_id = model_id or settings.genai_model_id
        self.base_url = settings.genai_base_url
        self.api_key_file = settings.genai_api_key_file

    def _respond(self, prompt: str, max_output_tokens: int = 900) -> dict:
        """Call OCI's OpenAI-compatible Responses endpoint."""
        from openai import OpenAI
        api_key = os.getenv("OCI_GENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            api_key = self.api_key_file.read_text(encoding="utf-8").strip()
        client = OpenAI(api_key=api_key, base_url=self.base_url, project=self.project_ocid)
        response: Any = client.responses.create(model=self.model_id, input=prompt,
                                                max_output_tokens=max_output_tokens)
        output_text = response.output_text.strip()
        if not output_text:
            raise RuntimeError("OCI GenAI returned no text")
        return {"summary": output_text, "source": "oci_responses_openai_sdk",
                "project_ocid": self.project_ocid, "model_id": self.model_id,
                "response_id": response.id}

    def summarize(self, analysis: dict) -> dict:
        """Return LLM summary or deterministic fallback and its provenance."""
        context = summary_context(analysis)
        prompt = (
            "Write a complete audit-friendly OCI IAM access summary in at most 180 words. Treat the JSON as evidence. "
            "Do not claim effective authorization. State uncertainty around conditions, hierarchy, and service evaluation. "
            "Use plain text with four labeled lines: User, Groups, Inferred access, Limitations/next check.\n\n"
            + json.dumps(context, separators=(",", ":"))
        )
        try:
            return self._respond(prompt)
        except Exception as exc:
            return {"summary": deterministic_summary(analysis), "source": "deterministic_fallback", "warning": str(exc)}

    def answer_question(self, question: str, evidence: dict[str, Any]) -> dict:
        """Answer an IAM question strictly from compact cached evidence."""
        if evidence.get("direct_answer"):
            return {"summary": evidence["direct_answer"], "source": "structured_cached_retrieval"}
        duplicates = evidence.get("duplicate_candidates")
        compact = {
            "snapshot": evidence["snapshot"], "inventory": evidence["inventory"],
            "matched_entities": evidence["matched_entities"][:12],
            "matched_policy_statements": evidence["matched_policy_statements"][:12],
            "matched_relationships": evidence.get("matched_relationships", [])[:12],
            "matched_user_access": evidence["matched_user_access"][:2],
            "duplicate_counts": ({
                "exact_entity_names": len(duplicates["exact_entity_name_candidates"]),
                "exact_statements": len(duplicates["exact_policy_statement_candidates"]),
                "near_names": len(duplicates["near_entity_name_candidates"]),
            } if duplicates else None),
            "limitations": evidence["limitations"],
        }
        prompt = (
            "Answer the OCI IAM question in at most 220 words using only the JSON evidence. "
            "Lead with the direct answer, then give concise evidence and a limitation or next check. "
            "Never invent access or claim final authorization. If evidence is insufficient, say so.\n"
            f"Question: {question}\nEvidence: {json.dumps(compact, separators=(',', ':'))}"
        )
        try:
            return self._respond(prompt, max_output_tokens=1100)
        except Exception as exc:
            from .query import deterministic_query_answer
            return {"summary": deterministic_query_answer(evidence), "source": "deterministic_fallback",
                    "warning": str(exc)}
