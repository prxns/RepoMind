import json
import logging
from dataclasses import dataclass

import httpx
import pytest

from repomind.config import Settings
from repomind.providers import (
    DeterministicGroundedAnswer,
    Evidence,
    FailureCategory,
    GeneratedAnswer,
    ProviderChain,
    ProviderFailure,
    answer_from_evidence,
    answer_provider,
    valid_citations,
)


def evidence() -> list[Evidence]:
    return [
        Evidence(
            "S1",
            "source-1",
            "apps/api/repomind/retrieval.py",
            41,
            58,
            "def reciprocal_rank_fusion(pools):\n    return combine_ranked_candidates(pools)",
            0.91,
        ),
        Evidence(
            "S2",
            "source-2",
            "apps/api/tests/test_retrieval.py",
            10,
            20,
            "def test_rrf_rewards_results_in_both_pools():\n    assert results[0] == shared",
            0.82,
        ),
    ]


@dataclass
class FakeProvider:
    provider_id: str
    provider_label: str
    result: GeneratedAnswer | None = None
    failure: ProviderFailure | None = None
    calls: int = 0

    def generate(self, question: str, selected: list[Evidence]) -> GeneratedAnswer:
        self.calls += 1
        if self.failure:
            raise self.failure
        assert self.result is not None
        return self.result


def failing(
    provider_id: str,
    label: str,
    category: FailureCategory = FailureCategory.TEMPORARILY_UNAVAILABLE,
    transient: bool = True,
    stop_chain: bool = False,
) -> FakeProvider:
    return FakeProvider(
        provider_id,
        label,
        failure=ProviderFailure(provider_id, label, category, transient, stop_chain),
    )


def test_primary_gemini_success_stops_chain():
    primary = FakeProvider(
        "gemini-3.8-flash",
        "Gemini 3.8 Flash",
        GeneratedAnswer("RRF combines both lists [S1].", ["S1"]),
    )
    secondary = FakeProvider(
        "gemini-3.7-flash",
        "Gemini 3.7 Flash",
        GeneratedAnswer("unused", []),
    )

    result = ProviderChain([primary, secondary]).generate("How is retrieval fused?", evidence())

    assert result.selected_provider == "gemini-3.8-flash"
    assert result.mode == "ai"
    assert result.attempted_providers == ["gemini-3.8-flash"]
    assert result.fallback_occurred is False
    assert primary.calls == 1 and secondary.calls == 0


def test_transient_primary_failure_uses_secondary_once():
    primary = failing("gemini-3.8-flash", "Gemini 3.8 Flash", FailureCategory.RATE_LIMITED)
    secondary = FakeProvider(
        "gemini-3.7-flash",
        "Gemini 3.7 Flash",
        GeneratedAnswer("RRF combines both lists [S1].", ["S1"]),
    )

    result = ProviderChain([primary, secondary]).generate("How is retrieval fused?", evidence())

    assert result.selected_provider == "gemini-3.7-flash"
    assert result.mode == "fallback_ai"
    assert result.attempted_providers == ["gemini-3.8-flash", "gemini-3.7-flash"]
    assert result.failures[0].category == FailureCategory.RATE_LIMITED
    assert result.notice == (
        "Gemini 3.8 Flash is rate limited. "
        "This response was generated using Gemini 3.7 Flash."
    )
    assert primary.calls == 1 and secondary.calls == 1


def test_two_transient_failures_use_deterministic_fallback():
    primary = failing("gemini-3.8-flash", "Gemini 3.8 Flash")
    secondary = failing("gemini-3.7-flash", "Gemini 3.7 Flash", FailureCategory.TIMEOUT)

    result = ProviderChain([primary, secondary]).generate("How is retrieval fused?", evidence())

    assert result.selected_provider == "deterministic-grounded"
    assert result.mode == "deterministic"
    assert result.generated.citation_ids == ["S1", "S2"]
    assert result.notice == (
        "Gemini 3.8 Flash and Gemini 3.7 Flash are temporarily unavailable. "
        "This response uses RepoMind's grounded fallback mode."
    )
    assert primary.calls == 1 and secondary.calls == 1


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Where is result fusion implemented?", "strongest matching evidence"),
        ("How are retrieval results fused?", "implementation flow"),
        ("Which tests cover RRF?", "Relevant test evidence"),
    ],
)
def test_deterministic_fallback_is_human_readable_and_grounded(question: str, expected: str):
    result = DeterministicGroundedAnswer().generate(question, evidence())

    assert expected in result.answer
    assert "`apps/api/repomind/retrieval.py` (lines 41–58)" in result.answer
    assert "function `reciprocal_rank_fusion`" in result.answer
    assert "[S1]" in result.answer
    assert "Relevant repository evidence:" not in result.answer
    assert result.citation_ids == ["S1", "S2"]


def test_invalid_citation_ids_and_markers_are_removed():
    result = valid_citations(
        GeneratedAnswer("Fusion happens here [S1]. Invented [S99].", ["S1", "S99"]),
        evidence(),
    )

    assert result.citation_ids == ["S1"]
    assert "[S1]" in result.answer
    assert "[S99]" not in result.answer


def test_irrelevant_question_skips_every_provider_call():
    provider = FakeProvider(
        "gemini-3.8-flash",
        "Gemini 3.8 Flash",
        GeneratedAnswer("should not run", []),
    )

    result = answer_from_evidence(
        "Who is the current CEO of Microsoft?", evidence(), False, ProviderChain([provider])
    )

    assert provider.calls == 0
    assert result.mode == "insufficient_evidence"
    assert result.generated.citation_ids == []
    assert result.generated.answer == (
        "I don't have enough evidence in the indexed repository to answer that question."
    )


def test_relevant_question_allows_provider_call():
    provider = FakeProvider(
        "gemini-3.8-flash",
        "Gemini 3.8 Flash",
        GeneratedAnswer("Fusion happens here [S1].", ["S1"]),
    )

    result = answer_from_evidence(
        "How are retrieval results fused?", evidence(), True, ProviderChain([provider])
    )

    assert provider.calls == 1
    assert result.selected_provider == "gemini-3.8-flash"


def test_current_interactions_contract_uses_strict_structured_output():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        answer = json.dumps({"answer": "Fusion happens here [S1].", "citations": ["S1"]})
        return httpx.Response(200, json={"steps": [{"type": "model_output", "content": [
            {"type": "text", "text": answer},
        ]}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    settings = Settings(
        _env_file=None,
        gemini_api_key="test-placeholder",
        gemini_primary_model="gemini-3.8-flash",
        gemini_secondary_model="gemini-3.7-flash",
    )

    result = answer_provider(settings, client).generate("How are results fused?", evidence())

    payload = json.loads(requests[0].content)
    assert requests[0].url == httpx.URL(
        "https://generativelanguage.googleapis.com/v1/interactions"
    )
    assert requests[0].headers["x-goog-api-key"] == "test-placeholder"
    assert payload["model"] == "gemini-3.8-flash"
    assert payload["store"] is False
    assert payload["response_format"]["mime_type"] == "application/json"
    assert payload["response_format"]["schema"]["additionalProperties"] is False
    assert "generation_config" not in payload
    assert not {"temperature", "top_p", "top_k", "candidate_count"} & payload.keys()
    assert result.selected_provider == "gemini-3.8-flash"


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_gemini_transient_http_failure_advances_to_secondary(status: int):
    attempted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        attempted.append(model)
        if model == "gemini-3.8-flash":
            return httpx.Response(status, json={"error": {"message": "safe mock failure"}})
        answer = json.dumps({"answer": "Fusion happens here [S1].", "citations": ["S1"]})
        return httpx.Response(200, json={"steps": [{"type": "model_output", "content": [
            {"type": "text", "text": answer},
        ]}]})

    settings = Settings(_env_file=None, gemini_api_key="test-placeholder")
    result = answer_provider(
        settings, httpx.Client(transport=httpx.MockTransport(handler))
    ).generate("How are results fused?", evidence())

    assert attempted == ["gemini-3.8-flash", "gemini-3.7-flash"]
    assert result.selected_provider == "gemini-3.7-flash"
    assert result.mode == "fallback_ai"


def test_gemini_connection_failures_reach_deterministic_fallback():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("mock connection failure", request=request)

    settings = Settings(_env_file=None, gemini_api_key="test-placeholder")
    result = answer_provider(
        settings, httpx.Client(transport=httpx.MockTransport(handler))
    ).generate("How are results fused?", evidence())

    assert result.attempted_providers == ["gemini-3.8-flash", "gemini-3.7-flash"]
    assert result.selected_provider == "deterministic-grounded"
    assert all(failure.transient for failure in result.failures)


def test_permanent_authentication_failure_is_safe_and_does_not_leak_key(caplog):
    secret = "AIza" + "A" * 35

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {
            "code": "authentication",
            "message": f"invalid credential {secret}",
        }})

    caplog.set_level(logging.WARNING, logger="repomind.providers")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    settings = Settings(_env_file=None, gemini_api_key=secret)
    assert secret not in repr(settings)

    result = answer_provider(settings, client).generate("How are results fused?", evidence())
    serialized = json.dumps(result.metadata())

    assert result.attempted_providers == ["gemini-3.8-flash"]
    assert result.selected_provider == "deterministic-grounded"
    assert result.failures[0].category == FailureCategory.AUTHENTICATION
    assert "could not authenticate" in result.notice
    assert secret not in serialized
    assert secret not in caplog.text


def test_missing_key_uses_clear_deterministic_configuration_state():
    result = answer_provider(Settings(_env_file=None)).generate(
        "How are results fused?", evidence()
    )

    assert result.attempted_providers == []
    assert result.selected_provider == "deterministic-grounded"
    assert result.failures[0].category == FailureCategory.NOT_CONFIGURED
    assert result.notice == (
        "Gemini generation is not configured. Showing RepoMind's grounded fallback answer."
    )
