"""Test suite for Milestone 3 integration: llm_client, verifier, and workflow.

Verifies:
1. llm_client constants, Bearer normalization, <think> tag stripping, and safety source compatibility.
2. verifier.py Invariants A, B, C, D, E, provenance audit, secret sanitization, and trace emission.
3. workflow.py solve_case and create_fallback_output schema conformance and zero-crash guarantee.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from student_agent.contracts import Contracts
from student_agent.llm_client import (
    DEFAULT_NVIDIA_API_KEY,
    DEFAULT_NVIDIA_MODEL,
    NvidiaLLMClient,
    SafetyEvaluationResult,
)
from student_agent.models import (
    AffectedEntities,
    Assessment,
    CaseInput,
    CaseInvestigationState,
    CaseStatus,
    ClaimAssessment,
    ClaimVerdict,
    CustomerClaim,
    CustomerRequest,
    DataConflict,
    FinancialResolution,
    PartyType,
    PolicyDecision,
    PrimaryIssue,
    RankedCause,
    RefundLine,
    ResponsibleParty,
    RootCauseAnalysis,
)
from student_agent.trace import TraceWriter
from student_agent.verifier import InvariantViolationError, VerifierAgent
from student_agent.workflow import create_fallback_output, solve_case


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def contracts_fixture() -> Contracts:
    schema_dir = Path(__file__).resolve().parents[1] / "contracts" / "schemas"
    return Contracts(schema_dir)


@pytest.fixture
def temp_trace_writer(tmp_path: Path, contracts_fixture: Contracts) -> TraceWriter:
    trace_path = tmp_path / "traces" / "test_trace.jsonl"
    return TraceWriter(trace_path, contracts_fixture)


def _make_state(case_id: str = "CASE_TEST_M3_001", order_id: str = "ord_test_001") -> CaseInvestigationState:
    case_input = CaseInput(
        case_id=case_id,
        opened_at="2026-09-25T00:00:00Z",
        customer_request=CustomerRequest(
            language="vi",
            message="Đơn hàng chưa nhận được",
            claimed_order_id=order_id,
            claims=(
                CustomerClaim(
                    claim_id="claim_001",
                    topic="delivery_delay",
                    detail="Chưa nhận được hàng",
                ),
            ),
        ),
        policy_version="EC_POLICY_V1",
    )
    return CaseInvestigationState(case_input=case_input)


# ==============================================================================
# 1. LLM CLIENT TESTS
# ==============================================================================

def test_llm_client_constants_and_bearer_normalization() -> None:
    """Verify DEFAULT constants match ORIGINAL_REQUEST.md and Bearer prefix is stripped."""
    assert DEFAULT_NVIDIA_MODEL == "deepseek-ai/deepseek-v4.1-flash"
    assert DEFAULT_NVIDIA_API_KEY == "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"

    # Test Bearer prefix stripping
    client_raw = NvidiaLLMClient(api_key="Bearer nvapi-test-key-12345678")
    assert client_raw._api_key == "nvapi-test-key-12345678"

    # Test clean key without prefix
    client_clean = NvidiaLLMClient(api_key="nvapi-clean-key-12345678")
    assert client_clean._api_key == "nvapi-clean-key-12345678"

    # Test backward compatibility of source in SafetyEvaluationResult
    res = SafetyEvaluationResult(
        is_safe=True,
        risk_category="safe",
        risk_score=0.0,
        reasoning="All clean",
    )
    assert res.source == "nvidia_nemotron_guard"


def test_llm_client_extract_json_with_think_tags() -> None:
    """Verify _extract_json strips DeepSeek <think> reasoning tags cleanly."""
    client = NvidiaLLMClient()

    raw_with_think = """<think>
Here is my internal reasoning about the customer's request.
The customer seems unhappy: {nested: "fake_brace"}
</think>
```json
{
  "is_safe": true,
  "risk_category": "safe",
  "risk_score": 0.0,
  "reasoning": "Văn bản an toàn."
}
```"""

    parsed = client._extract_json(raw_with_think)
    assert parsed is not None
    assert parsed["is_safe"] is True
    assert parsed["risk_category"] == "safe"
    assert parsed["risk_score"] == 0.0


# ==============================================================================
# 2. VERIFIER AGENT TESTS
# ==============================================================================

def test_verifier_invariant_a_no_action_and_needs_investigation(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter
) -> None:
    """Invariant A: no_action and needs_investigation must force recommended_refund_brl == 0.0 and refund_lines == []."""
    verifier = VerifierAgent(contracts=contracts_fixture, trace=temp_trace_writer)
    state = _make_state("CASE_INV_A_001")
    state.consumed_evidence_refs = {"ev_test_record_000000000000000001"}

    # Case 1: no_action with rogue non-zero refund
    decision_no_action = PolicyDecision(
        assessment=Assessment(
            primary_issue=PrimaryIssue.UNSUPPORTED_CLAIM,
            case_status=CaseStatus.NO_ACTION,
            confidence=0.95,
        ),
        affected_entities=AffectedEntities(order_ids=["ord_test_001"]),
        root_cause_analysis=RootCauseAnalysis(
            ranked_causes=[RankedCause("CLAIM_UNFOUNDED_BY_BUYER", 1)],
            responsible_parties=[ResponsibleParty(PartyType.CUSTOMER, "cust_001")],
        ),
        financial_resolution=FinancialResolution(
            currency="BRL",
            recommended_refund_brl=150.0,  # Rogue value
            refund_lines=[RefundLine("ROGUE_REFUND", 150.0, "ord_test_001")],
        ),
        evidence_refs=["ev_test_record_000000000000000001"],
        resolution_actions=["NO_FURTHER_ACTION_NEEDED"],
    )

    output = verifier.verify_and_assemble(state, decision_no_action, trace=temp_trace_writer)
    assert output["financial_resolution"]["recommended_refund_brl"] == 0.0
    assert output["financial_resolution"]["refund_lines"] == []
    contracts_fixture.validate_output(output, "test_inv_a_no_action")

    # Case 2: needs_investigation with rogue non-zero refund
    decision_needs_inv = PolicyDecision(
        assessment=Assessment(
            primary_issue=PrimaryIssue.INSUFFICIENT_EVIDENCE,
            case_status=CaseStatus.NEEDS_INVESTIGATION,
            confidence=0.50,
        ),
        affected_entities=AffectedEntities(order_ids=["ord_test_001"]),
        root_cause_analysis=RootCauseAnalysis(
            ranked_causes=[RankedCause("SYSTEM_INVESTIGATION_COMPLETED", 1)],
            responsible_parties=[ResponsibleParty(PartyType.UNKNOWN, None)],
        ),
        financial_resolution=FinancialResolution(
            currency="BRL",
            recommended_refund_brl=50.0,  # Rogue value
            refund_lines=[RefundLine("ROGUE_REFUND", 50.0, "ord_test_001")],
        ),
        evidence_refs=["ev_test_record_000000000000000001"],
        resolution_actions=["REQUEST_ADDITIONAL_CUSTOMER_EVIDENCE"],
    )

    output2 = verifier.verify_and_assemble(state, decision_needs_inv, trace=temp_trace_writer)
    assert output2["financial_resolution"]["recommended_refund_brl"] == 0.0
    assert output2["financial_resolution"]["refund_lines"] == []
    contracts_fixture.validate_output(output2, "test_inv_a_needs_inv")


def test_verifier_invariant_b_action_required_arithmetic_consistency(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter
) -> None:
    """Invariant B: action_required must reconcile recommended_refund_brl == round(sum(lines), 2)."""
    verifier = VerifierAgent(contracts=contracts_fixture, trace=temp_trace_writer)
    state = _make_state("CASE_INV_B_001")
    state.consumed_evidence_refs = {"ev_test_record_000000000000000001"}

    # Lines sum to 125.50 but total says 200.0 -> must reconcile to 125.50
    decision = PolicyDecision(
        assessment=Assessment(
            primary_issue=PrimaryIssue.CANCELED_ORDER_PAID,
            case_status=CaseStatus.ACTION_REQUIRED,
            confidence=0.98,
        ),
        affected_entities=AffectedEntities(order_ids=["ord_test_001"]),
        root_cause_analysis=RootCauseAnalysis(
            ranked_causes=[RankedCause("ORDER_CANCELED_POST_PAYMENT", 1)],
            responsible_parties=[ResponsibleParty(PartyType.PLATFORM, "olist_platform")],
        ),
        financial_resolution=FinancialResolution(
            currency="BRL",
            recommended_refund_brl=200.0,
            refund_lines=[
                RefundLine("FULL_ORDER_REFUND", 100.25, "ord_test_001"),
                RefundLine("SHIPPING_FEE_REFUND", 25.25, "ord_test_001"),
            ],
        ),
        evidence_refs=["ev_test_record_000000000000000001"],
        resolution_actions=["APPROVE_FULL_REFUND"],
    )

    output = verifier.verify_and_assemble(state, decision, trace=temp_trace_writer)
    assert output["financial_resolution"]["recommended_refund_brl"] == 125.50
    contracts_fixture.validate_output(output, "test_inv_b")


def test_verifier_invariant_c_provenance_audit(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter
) -> None:
    """Invariant C: Unconsumed or hallucinated evidence_refs are strictly purged."""
    verifier = VerifierAgent(contracts=contracts_fixture, trace=temp_trace_writer)
    state = _make_state("CASE_INV_C_001")
    # Only ev_genuine_01 was consumed
    genuine_ref = "ev_genuine_01_000000000000000001"
    hallucinated_ref = "ev_hallucinated_fake_000000000099"
    state.consumed_evidence_refs = {genuine_ref}

    decision = PolicyDecision(
        assessment=Assessment(
            primary_issue=PrimaryIssue.UNSUPPORTED_CLAIM,
            case_status=CaseStatus.NO_ACTION,
            confidence=0.95,
        ),
        affected_entities=AffectedEntities(order_ids=["ord_test_001"]),
        root_cause_analysis=RootCauseAnalysis(
            ranked_causes=[RankedCause("CLAIM_UNFOUNDED_BY_BUYER", 1)],
            responsible_parties=[ResponsibleParty(PartyType.CUSTOMER, "cust_001")],
        ),
        financial_resolution=FinancialResolution(
            currency="BRL",
            recommended_refund_brl=0.0,
            refund_lines=[],
        ),
        evidence_refs=[genuine_ref, hallucinated_ref],
        claim_assessments=[
            ClaimAssessment(
                claim_id="claim_001",
                verdict=ClaimVerdict.UNSUPPORTED,
                confidence=0.95,
                evidence_refs=[genuine_ref, hallucinated_ref],
            )
        ],
        resolution_actions=["NO_FURTHER_ACTION_NEEDED"],
    )

    output = verifier.verify_and_assemble(state, decision, trace=temp_trace_writer)
    assert hallucinated_ref not in output["evidence_refs"]
    assert genuine_ref in output["evidence_refs"]
    assert hallucinated_ref not in output["claim_assessments"][0]["evidence_refs"]
    assert genuine_ref in output["claim_assessments"][0]["evidence_refs"]
    contracts_fixture.validate_output(output, "test_inv_c")


def test_verifier_invariant_d_secret_leak_prevention(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter
) -> None:
    """Invariant D: Secret API keys in output strings are sanitized to [REDACTED]."""
    verifier = VerifierAgent(contracts=contracts_fixture, trace=temp_trace_writer)
    state = _make_state("CASE_INV_D_001")
    state.consumed_evidence_refs = {"ev_test_record_000000000000000001"}

    decision = PolicyDecision(
        assessment=Assessment(
            primary_issue=PrimaryIssue.UNSUPPORTED_CLAIM,
            case_status=CaseStatus.NO_ACTION,
            confidence=0.95,
        ),
        affected_entities=AffectedEntities(order_ids=["ord_test_001"]),
        root_cause_analysis=RootCauseAnalysis(
            ranked_causes=[RankedCause("CLAIM_UNFOUNDED_BY_BUYER", 1)],
            responsible_parties=[ResponsibleParty(PartyType.CUSTOMER, "cust_001")],
        ),
        financial_resolution=FinancialResolution(
            currency="BRL",
            recommended_refund_brl=0.0,
            refund_lines=[],
        ),
        evidence_refs=["ev_test_record_000000000000000001"],
        resolution_actions=[
            "NO_ACTION_KEY_sk-team-12345678_EXPOSED",
            "BEARER_AUTH_bearer nvapi-je_vL73TA7gCliG1fB_hAWJu",
        ],
    )

    output = verifier.verify_and_assemble(state, decision, trace=temp_trace_writer)
    serialized = json.dumps(output)
    assert "sk-team-12345678" not in serialized
    assert "nvapi-je_vL73TA7gCliG1fB_hAWJu" not in serialized
    assert "[REDACTED]" in serialized
    contracts_fixture.validate_output(output, "test_inv_d")


def test_verifier_purges_invalid_data_conflicts(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter
) -> None:
    """Schema requires minItems: 2 for sources in data_conflicts; single-source conflicts must be purged."""
    verifier = VerifierAgent(contracts=contracts_fixture, trace=temp_trace_writer)
    state = _make_state("CASE_CONFLICT_001")
    state.consumed_evidence_refs = {"ev_test_record_000000000000000001"}

    decision = PolicyDecision(
        assessment=Assessment(
            primary_issue=PrimaryIssue.UNSUPPORTED_CLAIM,
            case_status=CaseStatus.NO_ACTION,
            confidence=0.95,
        ),
        affected_entities=AffectedEntities(order_ids=["ord_test_001"]),
        root_cause_analysis=RootCauseAnalysis(
            ranked_causes=[RankedCause("CLAIM_UNFOUNDED_BY_BUYER", 1)],
            responsible_parties=[ResponsibleParty(PartyType.CUSTOMER, "cust_001")],
        ),
        financial_resolution=FinancialResolution(
            currency="BRL",
            recommended_refund_brl=0.0,
            refund_lines=[],
        ),
        evidence_refs=["ev_test_record_000000000000000001"],
        data_conflicts=[
            DataConflict(
                field="order_status",
                sources=["order_db"],  # Only 1 source -> violates schema minItems: 2
                selected_source="order_db",
                resolution_code="FAVOR_ORDER_DB",
            ),
            DataConflict(
                field="payment_status",
                sources=["payment_gateway", "order_db"],  # 2 sources -> valid!
                selected_source="payment_gateway",
                resolution_code="FAVOR_PAYMENT_GATEWAY",
            ),
        ],
        resolution_actions=["NO_FURTHER_ACTION_NEEDED"],
    )

    output = verifier.verify_and_assemble(state, decision, trace=temp_trace_writer)
    assert len(output["data_conflicts"]) == 1
    assert output["data_conflicts"][0]["field"] == "payment_status"
    contracts_fixture.validate_output(output, "test_conflicts")


# ==============================================================================
# 3. WORKFLOW TESTS: FALLBACK AND END-TO-END
# ==============================================================================

def test_workflow_create_fallback_output(contracts_fixture: Contracts, temp_trace_writer: TraceWriter) -> None:
    """Verify create_fallback_output generates valid schema output and emits required emergency traces."""
    case = {
        "case_id": "CASE_ERR_001",
        "opened_at": "2026-09-25T00:00:00Z",
        "customer_request": {
            "claimed_order_id": "ord_fallback_001",
            "claims": [{"claim_id": "claim_001"}],
        },
    }

    fallback_output = create_fallback_output(
        case=case,
        trace=temp_trace_writer,
        error=RuntimeError("Simulated catastrophic failure"),
        contracts=contracts_fixture,
    )

    assert fallback_output["case_id"] == "CASE_ERR_001"
    assert fallback_output["assessment"]["primary_issue"] == "insufficient_evidence"
    assert fallback_output["assessment"]["case_status"] == "needs_investigation"
    assert fallback_output["financial_resolution"]["recommended_refund_brl"] == 0.0
    assert fallback_output["financial_resolution"]["refund_lines"] == []
    contracts_fixture.validate_output(fallback_output, "test_fallback")


@pytest.mark.asyncio
async def test_workflow_solve_case_recovers_gracefully_from_gateway_error(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter
) -> None:
    """Verify solve_case catches unhandled exceptions and returns a valid fallback output."""
    class FailingGateway:
        async def list_tools(self) -> list[str]:
            raise ConnectionError("Simulated MCP Gateway network down")

        async def call(self, tool_name: str, *, case_id: str, **arguments: str) -> dict[str, Any]:
            raise ConnectionError("Network down")

    case = {
        "case_id": "CASE_RECOVER_001",
        "opened_at": "2026-09-25T00:00:00Z",
        "policy_version": "EC_POLICY_V1",
        "customer_request": {
            "language": "vi",
            "message": "Không thể kết nối",
            "claimed_order_id": "ord_rec_001",
            "claims": [{"claim_id": "claim_001"}],
        },
    }

    output = await solve_case(
        case=case,
        gateway=FailingGateway(),  # type: ignore[arg-type]
        trace=temp_trace_writer,
        contracts=contracts_fixture,
    )

    assert output["case_id"] == "CASE_RECOVER_001"
    assert output["assessment"]["primary_issue"] == "insufficient_evidence"
    assert output["assessment"]["case_status"] == "needs_investigation"
    contracts_fixture.validate_output(output, "test_solve_case_recovery")


@pytest.mark.asyncio
async def test_workflow_solve_case_end_to_end_success(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter
) -> None:
    """Verify solve_case runs full multi-agent pipeline with mock gateway and produces schema-valid output."""
    class FullMockGateway:
        async def list_tools(self) -> list[str]:
            return ["get_order", "get_payment", "get_shipment", "get_refund"]

        async def call(self, tool_name: str, *, case_id: str, **arguments: str) -> dict[str, Any]:
            if tool_name == "get_order":
                return {
                    "evidence_ref": "ev_order_data_record_000000000000000001",
                    "domain": "order",
                    "result_hash": "hash_order_12345",
                    "data": {
                        "order_id": arguments.get("order_id", "ord_full_001"),
                        "status": "canceled",
                        "customer_id": "cust_full_001",
                        "order_purchase_timestamp": "2026-09-01T10:00:00Z",
                        "items": [
                            {
                                "item_id": "item_full_001",
                                "seller_id": "seller_full_001",
                                "price": 120.0,
                                "freight_value": 30.0,
                            }
                        ],
                    },
                    "warnings": [],
                }
            elif tool_name == "get_payment":
                return {
                    "evidence_ref": "ev_payment_data_record_0000000000000002",
                    "domain": "payment",
                    "result_hash": "hash_pay_12345",
                    "data": {
                        "order_id": arguments.get("order_id", "ord_full_001"),
                        "total_paid": 150.0,
                        "payments": [
                            {
                                "payment_sequential": 1,
                                "payment_type": "credit_card",
                                "payment_installments": 1,
                                "payment_value": 150.0,
                            }
                        ],
                    },
                    "warnings": [],
                }
            elif tool_name == "get_refund":
                return {
                    "evidence_ref": "ev_refund_data_record_0000000000000003",
                    "domain": "refund",
                    "result_hash": "hash_ref_12345",
                    "data": {
                        "order_id": arguments.get("order_id", "ord_full_001"),
                        "refund_status": "none",
                        "refunded_amount": 0.0,
                    },
                    "warnings": [],
                }
            elif tool_name == "get_shipment":
                return {
                    "evidence_ref": "ev_shipment_data_record_00000000000004",
                    "domain": "shipment",
                    "result_hash": "hash_ship_12345",
                    "data": {
                        "order_id": arguments.get("order_id", "ord_full_001"),
                        "shipment_id": "ship_full_001",
                        "carrier_partner": "correios",
                        "order_delivered_customer_date": None,
                        "order_estimated_delivery_date": "2026-09-10T00:00:00Z",
                    },
                    "warnings": [],
                }
            return {
                "evidence_ref": "ev_default_data_record_00000000000005",
                "domain": "order",
                "result_hash": "hash_default",
                "data": {},
                "warnings": [],
            }

    case = {
        "case_id": "CASE_FULL_001",
        "opened_at": "2026-09-25T00:00:00Z",
        "policy_version": "EC_POLICY_V1",
        "customer_request": {
            "language": "vi",
            "message": "Đơn hàng của tôi bị hủy nhưng tôi đã thanh toán 150 BRL và chưa nhận lại tiền.",
            "claimed_order_id": "ord_full_001",
            "claims": [
                {
                    "claim_id": "claim_001",
                    "topic": "canceled_order_paid",
                    "detail": "Đã thanh toán nhưng đơn bị hủy chưa được hoàn tiền",
                }
            ],
        },
    }

    output = await solve_case(
        case=case,
        gateway=FullMockGateway(),  # type: ignore[arg-type]
        trace=temp_trace_writer,
        contracts=contracts_fixture,
    )

    assert output["case_id"] == "CASE_FULL_001"
    assert output["assessment"]["primary_issue"] == "canceled_order_paid"
    assert output["assessment"]["case_status"] == "action_required"
    assert output["financial_resolution"]["recommended_refund_brl"] == 150.0
    contracts_fixture.validate_output(output, "test_full_e2e")
