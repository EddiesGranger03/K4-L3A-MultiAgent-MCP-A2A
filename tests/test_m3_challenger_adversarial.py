"""Adversarial stress tests for VerifierAgent (Milestone 3.1).

Empirical Challenge Suite:
1. Financial reconciliation with extreme floating point amounts (0.1 + 0.2, 999.999 BRL, IEEE 754 edge cases).
2. Decision self-healing for no_action and needs_investigation with rogue non-zero refunds and lines.
3. Provenance audit and hallucination drop (including empty consumed_refs vulnerability).
4. Secret injection across various fields (sk-team-*, nvapi-*, short tokens, nested fields).
5. Data conflict validation (single source, duplicate sources, maxItems).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from student_agent.contracts import ContractError, Contracts
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


@pytest.fixture
def contracts_fixture() -> Contracts:
    schema_dir = Path(__file__).resolve().parents[1] / "contracts" / "schemas"
    return Contracts(schema_dir)


@pytest.fixture
def temp_trace_writer(tmp_path: Path, contracts_fixture: Contracts) -> TraceWriter:
    trace_path = tmp_path / "traces" / "test_adversarial_trace.jsonl"
    return TraceWriter(trace_path, contracts_fixture)


def _make_state(case_id: str = "CASE_ADV_001", order_id: str = "ord_adv_001") -> CaseInvestigationState:
    case_input = CaseInput(
        case_id=case_id,
        opened_at="2026-09-25T00:00:00Z",
        customer_request=CustomerRequest(
            language="vi",
            message="Adversarial challenge test case",
            claimed_order_id=order_id,
            claims=(
                CustomerClaim(
                    claim_id="claim_adv_001",
                    topic="delivery_delay",
                    detail="Chưa nhận được hàng",
                ),
            ),
        ),
        policy_version="EC_POLICY_V1",
    )
    return CaseInvestigationState(case_input=case_input)


# ==============================================================================
# CHALLENGE 1: FINANCIAL RECONCILIATION & FLOATING POINT EXTREMES
# ==============================================================================

def test_financial_reconciliation_floating_point_point_one_plus_two(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter
) -> None:
    """Challenge 1.1: 0.1 + 0.2 IEEE 754 precision reconciliation."""
    verifier = VerifierAgent(contracts=contracts_fixture, trace=temp_trace_writer)
    state = _make_state("CASE_FLOAT_001")
    state.consumed_evidence_refs = {"ev_test_record_000000000000000001"}

    # 0.1 + 0.2 in python is 0.30000000000000004
    decision = PolicyDecision(
        assessment=Assessment(
            primary_issue=PrimaryIssue.CANCELED_ORDER_PAID,
            case_status=CaseStatus.ACTION_REQUIRED,
            confidence=0.95,
        ),
        affected_entities=AffectedEntities(order_ids=["ord_adv_001"]),
        root_cause_analysis=RootCauseAnalysis(
            ranked_causes=[RankedCause("ORDER_CANCELED_POST_PAYMENT", 1)],
            responsible_parties=[ResponsibleParty(PartyType.PLATFORM, "olist_platform")],
        ),
        financial_resolution=FinancialResolution(
            currency="BRL",
            recommended_refund_brl=0.1 + 0.2,  # IEEE 754 float
            refund_lines=[
                RefundLine("ITEM_1", 0.1, "ord_adv_001"),
                RefundLine("ITEM_2", 0.2, "ord_adv_001"),
            ],
        ),
        evidence_refs=["ev_test_record_000000000000000001"],
        resolution_actions=["APPROVE_FULL_REFUND"],
    )

    output = verifier.verify_and_assemble(state, decision, trace=temp_trace_writer)
    assert output["financial_resolution"]["recommended_refund_brl"] == 0.3
    assert output["financial_resolution"]["refund_lines"][0]["amount_brl"] == 0.1
    assert output["financial_resolution"]["refund_lines"][1]["amount_brl"] == 0.2
    contracts_fixture.validate_output(output, "test_float_0_1_0_2")


def test_financial_reconciliation_extreme_fractions_999_999_brl(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter
) -> None:
    """Challenge 1.2: 999.999 BRL extreme fractional rounding."""
    verifier = VerifierAgent(contracts=contracts_fixture, trace=temp_trace_writer)
    state = _make_state("CASE_FLOAT_002")
    state.consumed_evidence_refs = {"ev_test_record_000000000000000001"}

    decision = PolicyDecision(
        assessment=Assessment(
            primary_issue=PrimaryIssue.CANCELED_ORDER_PAID,
            case_status=CaseStatus.ACTION_REQUIRED,
            confidence=0.95,
        ),
        affected_entities=AffectedEntities(order_ids=["ord_adv_001"]),
        root_cause_analysis=RootCauseAnalysis(
            ranked_causes=[RankedCause("ORDER_CANCELED_POST_PAYMENT", 1)],
            responsible_parties=[ResponsibleParty(PartyType.PLATFORM, "olist_platform")],
        ),
        financial_resolution=FinancialResolution(
            currency="BRL",
            recommended_refund_brl=999.999,
            refund_lines=[
                RefundLine("OVERCHARGED_ITEM", 999.999, "ord_adv_001"),
            ],
        ),
        evidence_refs=["ev_test_record_000000000000000001"],
        resolution_actions=["APPROVE_FULL_REFUND"],
    )

    output = verifier.verify_and_assemble(state, decision, trace=temp_trace_writer)
    # 999.999 rounded to 2 decimals is 1000.00
    assert output["financial_resolution"]["recommended_refund_brl"] == 1000.0
    assert output["financial_resolution"]["refund_lines"][0]["amount_brl"] == 1000.0
    contracts_fixture.validate_output(output, "test_float_999_999")


def test_financial_reconciliation_empty_lines_auto_creation(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter
) -> None:
    """Challenge 1.3: action_required with refund amount but empty lines creates default line."""
    verifier = VerifierAgent(contracts=contracts_fixture, trace=temp_trace_writer)
    state = _make_state("CASE_FLOAT_003")
    state.consumed_evidence_refs = {"ev_test_record_000000000000000001"}

    decision = PolicyDecision(
        assessment=Assessment(
            primary_issue=PrimaryIssue.CANCELED_ORDER_PAID,
            case_status=CaseStatus.ACTION_REQUIRED,
            confidence=0.95,
        ),
        affected_entities=AffectedEntities(order_ids=["ord_adv_001"]),
        root_cause_analysis=RootCauseAnalysis(
            ranked_causes=[RankedCause("ORDER_CANCELED_POST_PAYMENT", 1)],
            responsible_parties=[ResponsibleParty(PartyType.PLATFORM, "olist_platform")],
        ),
        financial_resolution=FinancialResolution(
            currency="BRL",
            recommended_refund_brl=250.75,
            refund_lines=[],  # Missing refund lines!
        ),
        evidence_refs=["ev_test_record_000000000000000001"],
        resolution_actions=["APPROVE_FULL_REFUND"],
    )

    output = verifier.verify_and_assemble(state, decision, trace=temp_trace_writer)
    assert output["financial_resolution"]["recommended_refund_brl"] == 250.75
    assert len(output["financial_resolution"]["refund_lines"]) == 1
    assert output["financial_resolution"]["refund_lines"][0]["amount_brl"] == 250.75
    assert output["financial_resolution"]["refund_lines"][0]["reason_code"] == "APPROVED_CLAIM_REFUND"
    contracts_fixture.validate_output(output, "test_float_empty_lines")


def test_financial_reconciliation_more_than_ten_refund_lines_truncated(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter
) -> None:
    """Challenge 1.4: More than 10 refund lines are truncated to 10 and refund is reconciled."""
    verifier = VerifierAgent(contracts=contracts_fixture, trace=temp_trace_writer)
    state = _make_state("CASE_FLOAT_004")
    state.consumed_evidence_refs = {"ev_test_record_000000000000000001"}

    # 15 lines of 10.0 each = 150.0 total claimed
    lines = [RefundLine(f"REASON_{i}", 10.0, f"ent_{i}") for i in range(15)]
    decision = PolicyDecision(
        assessment=Assessment(
            primary_issue=PrimaryIssue.CANCELED_ORDER_PAID,
            case_status=CaseStatus.ACTION_REQUIRED,
            confidence=0.95,
        ),
        affected_entities=AffectedEntities(order_ids=["ord_adv_001"]),
        root_cause_analysis=RootCauseAnalysis(
            ranked_causes=[RankedCause("ORDER_CANCELED_POST_PAYMENT", 1)],
            responsible_parties=[ResponsibleParty(PartyType.PLATFORM, "olist_platform")],
        ),
        financial_resolution=FinancialResolution(
            currency="BRL",
            recommended_refund_brl=150.0,
            refund_lines=lines,
        ),
        evidence_refs=["ev_test_record_000000000000000001"],
        resolution_actions=["APPROVE_FULL_REFUND"],
    )

    output = verifier.verify_and_assemble(state, decision, trace=temp_trace_writer)
    # Truncated to 10 lines, so sum of 10 lines is 100.0, recommended_refund must be 100.0
    assert len(output["financial_resolution"]["refund_lines"]) == 10
    assert output["financial_resolution"]["recommended_refund_brl"] == 100.0
    contracts_fixture.validate_output(output, "test_float_more_than_10_lines")


# ==============================================================================
# CHALLENGE 2: NO_ACTION & NEEDS_INVESTIGATION SELF-HEALING
# ==============================================================================

def test_no_action_enforces_zero_refund_and_empty_lines_and_safe_actions(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter
) -> None:
    """Challenge 2.1: no_action strictly forces 0.0 refund, [] lines, and removes refund actions."""
    verifier = VerifierAgent(contracts=contracts_fixture, trace=temp_trace_writer)
    state = _make_state("CASE_HEAL_001")
    state.consumed_evidence_refs = {"ev_test_record_000000000000000001"}

    decision = PolicyDecision(
        assessment=Assessment(
            primary_issue=PrimaryIssue.UNSUPPORTED_CLAIM,
            case_status=CaseStatus.NO_ACTION,
            confidence=0.99,
        ),
        affected_entities=AffectedEntities(order_ids=["ord_adv_001"]),
        root_cause_analysis=RootCauseAnalysis(
            ranked_causes=[RankedCause("CLAIM_UNFOUNDED_BY_BUYER", 1)],
            responsible_parties=[ResponsibleParty(PartyType.CUSTOMER, "cust_adv_001")],
        ),
        financial_resolution=FinancialResolution(
            currency="BRL",
            recommended_refund_brl=888.88,  # Rogue non-zero refund
            refund_lines=[
                RefundLine("ROGUE_LINE_1", 400.0, "ord_adv_001"),
                RefundLine("ROGUE_LINE_2", 488.88, "ord_adv_001"),
            ],
        ),
        evidence_refs=["ev_test_record_000000000000000001"],
        resolution_actions=[
            "APPROVE_FULL_REFUND",  # Disallowed for no_action
            "DISPATCH_REPLACEMENT_ITEM",  # Disallowed
        ],
    )

    output = verifier.verify_and_assemble(state, decision, trace=temp_trace_writer)
    assert output["financial_resolution"]["recommended_refund_brl"] == 0.0
    assert output["financial_resolution"]["refund_lines"] == []
    # Disallowed refund actions must be purged, defaulting to NO_FURTHER_ACTION_NEEDED
    assert "APPROVE_FULL_REFUND" not in output["resolution_actions"]
    assert "DISPATCH_REPLACEMENT_ITEM" not in output["resolution_actions"]
    assert output["resolution_actions"] == ["NO_FURTHER_ACTION_NEEDED"]
    contracts_fixture.validate_output(output, "test_no_action_healed")


def test_needs_investigation_enforces_zero_refund_and_empty_lines_and_audit_actions(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter
) -> None:
    """Challenge 2.2: needs_investigation strictly forces 0.0 refund, [] lines, and audit actions."""
    verifier = VerifierAgent(contracts=contracts_fixture, trace=temp_trace_writer)
    state = _make_state("CASE_HEAL_002")
    state.consumed_evidence_refs = {"ev_test_record_000000000000000001"}

    decision = PolicyDecision(
        assessment=Assessment(
            primary_issue=PrimaryIssue.INSUFFICIENT_EVIDENCE,
            case_status=CaseStatus.NEEDS_INVESTIGATION,
            confidence=0.45,
        ),
        affected_entities=AffectedEntities(order_ids=["ord_adv_001"]),
        root_cause_analysis=RootCauseAnalysis(
            ranked_causes=[RankedCause("SYSTEM_INVESTIGATION_COMPLETED", 1)],
            responsible_parties=[ResponsibleParty(PartyType.UNKNOWN, None)],
        ),
        financial_resolution=FinancialResolution(
            currency="BRL",
            recommended_refund_brl=123.45,  # Rogue non-zero refund
            refund_lines=[RefundLine("ROGUE_INVESTIGATION_LINE", 123.45, "ord_adv_001")],
        ),
        evidence_refs=["ev_test_record_000000000000000001"],
        resolution_actions=["APPROVE_PARTIAL_REFUND"],  # Disallowed
    )

    output = verifier.verify_and_assemble(state, decision, trace=temp_trace_writer)
    assert output["financial_resolution"]["recommended_refund_brl"] == 0.0
    assert output["financial_resolution"]["refund_lines"] == []
    assert "APPROVE_PARTIAL_REFUND" not in output["resolution_actions"]
    assert output["resolution_actions"] == [
        "REQUEST_ADDITIONAL_CUSTOMER_EVIDENCE",
        "OPEN_INTERNAL_AUDIT_INVESTIGATION",
    ]
    contracts_fixture.validate_output(output, "test_needs_inv_healed")


# ==============================================================================
# CHALLENGE 3: HALLUCINATED EVIDENCE REFS AUDIT
# ==============================================================================

def test_hallucinated_evidence_refs_strictly_dropped(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter
) -> None:
    """Challenge 3.1: Verifier drops unconsumed hallucinated refs and preserves genuine refs."""
    verifier = VerifierAgent(contracts=contracts_fixture, trace=temp_trace_writer)
    state = _make_state("CASE_HALLUCINATION_001")

    genuine_1 = "ev_genuine_order_record_00000000000001"
    genuine_2 = "ev_genuine_payment_record_000000000002"
    hallucinated_1 = "ev_hallucinated_fake_00000000000001"
    hallucinated_2 = "ev_invented_ref_not_in_mcp_0000000002"
    malformed_ref = "not_even_an_evidence_ref_format"

    state.consumed_evidence_refs = {genuine_1, genuine_2}

    decision = PolicyDecision(
        assessment=Assessment(
            primary_issue=PrimaryIssue.UNSUPPORTED_CLAIM,
            case_status=CaseStatus.NO_ACTION,
            confidence=0.90,
        ),
        affected_entities=AffectedEntities(order_ids=["ord_adv_001"]),
        root_cause_analysis=RootCauseAnalysis(
            ranked_causes=[RankedCause("CLAIM_UNFOUNDED_BY_BUYER", 1)],
            responsible_parties=[ResponsibleParty(PartyType.CUSTOMER, "cust_adv_001")],
        ),
        financial_resolution=FinancialResolution(
            currency="BRL",
            recommended_refund_brl=0.0,
            refund_lines=[],
        ),
        evidence_refs=[genuine_1, hallucinated_1, malformed_ref, genuine_2, hallucinated_2],
        claim_assessments=[
            ClaimAssessment(
                claim_id="claim_adv_001",
                verdict=ClaimVerdict.UNSUPPORTED,
                confidence=0.90,
                evidence_refs=[hallucinated_1, genuine_1, hallucinated_2],
            )
        ],
        resolution_actions=["NO_FURTHER_ACTION_NEEDED"],
    )

    output = verifier.verify_and_assemble(state, decision, trace=temp_trace_writer)
    assert genuine_1 in output["evidence_refs"]
    assert genuine_2 in output["evidence_refs"]
    assert hallucinated_1 not in output["evidence_refs"]
    assert hallucinated_2 not in output["evidence_refs"]
    assert malformed_ref not in output["evidence_refs"]

    # Claim assessment audit check
    claim_refs = output["claim_assessments"][0]["evidence_refs"]
    assert genuine_1 in claim_refs
    assert hallucinated_1 not in claim_refs
    assert hallucinated_2 not in claim_refs

    contracts_fixture.validate_output(output, "test_provenance_audit")


def test_flaw_hallucinated_refs_leak_when_consumed_refs_is_empty() -> None:
    """Challenge 3.2 [FLAW CONFIRMED]: When consumed_refs is empty, hallucinated refs are NOT dropped!

    In `_audit_evidence_provenance`:
        if consumed_refs and ref_str not in consumed_refs:
            ... continue
    Because `consumed_refs` is empty (set()), the condition evaluates to False!
    Thus, any hallucinated ref matching regex passes right through into output!
    """
    verifier = VerifierAgent()
    hallucinated_ref = "ev_hallucinated_fake_00000000000001"
    audited = verifier._audit_evidence_provenance(
        candidate_refs=[hallucinated_ref],
        consumed_refs=set(),
        case_id="CASE_BUG_EMPTY_REFS",
    )
    # The hallucinated ref leaked through because consumed_refs is empty!
    assert hallucinated_ref in audited, "Hallucinated ref was surprisingly dropped despite the bug"


# ==============================================================================
# CHALLENGE 4: SECRET INJECTION SCRUBBING
# ==============================================================================

def test_secret_injection_sk_team_scrubbed() -> None:
    """Challenge 4.1: sk-team-* keys are scrubbed to [REDACTED]."""
    verifier = VerifierAgent()
    raw = "My secret is sk-team-testkey12345"
    sanitized = verifier._sanitize_secrets(raw)
    assert sanitized == "My secret is [REDACTED]"
    assert "sk-team-testkey12345" not in sanitized


def test_flaw_secret_injection_nvapi_short_key_leaks() -> None:
    """Challenge 4.2 [FLAW CONFIRMED]: nvapi-testkey12345 LEAKS because regex requires {16,} chars!

    In `SECRET_PATTERNS`:
        re.compile(r"nvapi-[A-Za-z0-9_-]{16,}", re.IGNORECASE)
    'testkey12345' has only 12 characters.
    12 < 16, so `nvapi-testkey12345` is NOT matched and NOT scrubbed!
    """
    verifier = VerifierAgent()
    test_key = "nvapi-testkey12345"
    sanitized = verifier._sanitize_secrets(test_key)
    # Because len("testkey12345") == 12 < 16, it is NOT sanitized!
    assert sanitized == "nvapi-testkey12345", "nvapi-testkey12345 should have leaked due to {16,} quantifier"


def test_secret_injection_nvapi_long_key_is_scrubbed() -> None:
    """Challenge 4.3: nvapi-* with >=16 chars IS scrubbed."""
    verifier = VerifierAgent()
    long_key = "nvapi-1234567890123456"  # 16 chars
    sanitized = verifier._sanitize_secrets(long_key)
    assert sanitized == "[REDACTED]"


# ==============================================================================
# CHALLENGE 5: DATA CONFLICT SCHEMA COMPLIANCE (minItems: 2)
# ==============================================================================

def test_data_conflict_single_source_dropped_and_valid_retained(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter
) -> None:
    """Challenge 5.1: Single-source data conflicts must be dropped to satisfy minItems: 2."""
    verifier = VerifierAgent(contracts=contracts_fixture, trace=temp_trace_writer)
    state = _make_state("CASE_CONFLICT_001")
    state.consumed_evidence_refs = {"ev_test_record_000000000000000001"}

    decision = PolicyDecision(
        assessment=Assessment(
            primary_issue=PrimaryIssue.UNSUPPORTED_CLAIM,
            case_status=CaseStatus.NO_ACTION,
            confidence=0.95,
        ),
        affected_entities=AffectedEntities(order_ids=["ord_adv_001"]),
        root_cause_analysis=RootCauseAnalysis(
            ranked_causes=[RankedCause("CLAIM_UNFOUNDED_BY_BUYER", 1)],
            responsible_parties=[ResponsibleParty(PartyType.CUSTOMER, "cust_adv_001")],
        ),
        financial_resolution=FinancialResolution(
            currency="BRL",
            recommended_refund_brl=0.0,
            refund_lines=[],
        ),
        evidence_refs=["ev_test_record_000000000000000001"],
        data_conflicts=[
            DataConflict(
                field="single_source_field",
                sources=["order_db"],  # 1 source -> VIOLATION! Must be dropped!
                selected_source="order_db",
                resolution_code="FAVOR_ORDER_DB",
            ),
            DataConflict(
                field="zero_source_field",
                sources=[],  # 0 sources -> VIOLATION! Must be dropped!
                selected_source=None,
                resolution_code="NO_SOURCE",
            ),
            DataConflict(
                field="valid_dual_source_field",
                sources=["order_db", "payment_gateway"],  # 2 sources -> VALID!
                selected_source="payment_gateway",
                resolution_code="FAVOR_PAYMENT_GATEWAY",
            ),
        ],
        resolution_actions=["NO_FURTHER_ACTION_NEEDED"],
    )

    output = verifier.verify_and_assemble(state, decision, trace=temp_trace_writer)
    assert len(output["data_conflicts"]) == 1
    assert output["data_conflicts"][0]["field"] == "valid_dual_source_field"
    assert output["data_conflicts"][0]["sources"] == ["order_db", "payment_gateway"]
    contracts_fixture.validate_output(output, "test_conflicts_single_source_dropped")


def test_flaw_data_conflict_duplicate_sources_in_dict_causes_schema_crash(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter
) -> None:
    """Challenge 5.2 [FLAW CONFIRMED]: Raw dict data_conflicts with duplicates crash schema validation!

    If a data conflict is passed as a dict with duplicate sources e.g. `['s1', 's1']`,
    `VerifierAgent` only checks `len(sources) >= 2` (which is 2), so it is not dropped.
    Then `Contracts.validate_output` throws a ContractError because the schema specifies
    `uniqueItems: true` on `sources`!
    """
    verifier = VerifierAgent(contracts=contracts_fixture, trace=temp_trace_writer)
    state = _make_state("CASE_CONFLICT_DUP_CRASH")
    state.consumed_evidence_refs = {"ev_test_record_000000000000000001"}

    decision = PolicyDecision(
        assessment=Assessment(
            primary_issue=PrimaryIssue.UNSUPPORTED_CLAIM,
            case_status=CaseStatus.NO_ACTION,
            confidence=0.95,
        ),
        affected_entities=AffectedEntities(order_ids=["ord_adv_001"]),
        root_cause_analysis=RootCauseAnalysis(
            ranked_causes=[RankedCause("CLAIM_UNFOUNDED_BY_BUYER", 1)],
            responsible_parties=[ResponsibleParty(PartyType.CUSTOMER, "cust_adv_001")],
        ),
        financial_resolution=FinancialResolution(
            currency="BRL",
            recommended_refund_brl=0.0,
            refund_lines=[],
        ),
        evidence_refs=["ev_test_record_000000000000000001"],
        data_conflicts=[
            # Raw dict representation with duplicate sources
            {
                "field": "unnormalized_conflict",
                "sources": ["order_db", "order_db"],
                "selected_source": "order_db",
                "resolution_code": "FAVOR_ORDER_DB",
            },
        ],  # type: ignore[arg-type]
        resolution_actions=["NO_FURTHER_ACTION_NEEDED"],
    )

    with pytest.raises(InvariantViolationError, match="has non-unique elements"):
        verifier.verify_and_assemble(state, decision, trace=temp_trace_writer)
