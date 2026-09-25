"""Adversarial and comprehensive invariant verification tests for src/student_agent/models.py.

Covers:
- L3AOutputV2.to_dict() schema compliance against contracts/schemas/l3a-output-v2.schema.json
- L3AOutputV2.validate_invariants() under edge conditions:
  * case_status == 'no_action' with recommended_refund_brl > 0
  * case_status == 'no_action' with non-empty refund_lines
  * case_status == 'action_required' with mismatching refund sum
  * unprovenanced evidence_refs
  * empty arrays across all optional and required list fields
  * lists exceeding maxItems (deduplication & truncation)
  * duplicate items in affected_entities, evidence_refs, resolution_actions
  * boundary float values for confidence, refund amounts, and precision rounding
"""

from __future__ import annotations

from pathlib import Path

import pytest

from student_agent.contracts import Contracts
from student_agent.models import (
    CASE_ID_PATTERN,
    CURRENCY_BRL,
    EVIDENCE_REF_PATTERN,
    OUTPUT_SCHEMA_VERSION,
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
    L3AOutputV2,
    PartyType,
    PolicyDecision,
    PrimaryIssue,
    RankedCause,
    RefundLine,
    ResponsibleParty,
    RootCauseAnalysis,
)


@pytest.fixture
def contracts() -> Contracts:
    schema_dir = Path(__file__).resolve().parents[1] / "contracts" / "schemas"
    return Contracts(schema_dir)


def _make_valid_evidence_ref(suffix: int = 1) -> str:
    """Generate a valid evidence_ref matching ^ev_[A-Za-z0-9_-]{20,96}$."""
    return f"ev_audit_trace_record_{suffix:024d}"


def _make_base_output(
    case_id: str = "CASE_M1_TEST_001",
    status: CaseStatus = CaseStatus.NO_ACTION,
    primary_issue: PrimaryIssue = PrimaryIssue.UNSUPPORTED_CLAIM,
    confidence: float = 0.95,
    refund_amount: float = 0.0,
    refund_lines: list[RefundLine] | None = None,
    evidence_refs: list[str] | None = None,
    resolution_actions: list[str] | None = None,
    claim_assessments: list[ClaimAssessment] | None = None,
    data_conflicts: list[DataConflict] | None = None,
) -> L3AOutputV2:
    return L3AOutputV2(
        case_id=case_id,
        assessment=Assessment(primary_issue, status, confidence),
        affected_entities=AffectedEntities(
            order_ids=["ord_test_001"],
            item_ids=["item_001"],
            seller_ids=["seller_001"],
            payment_references=["pay_ref_001"],
            shipment_ids=["ship_001"],
        ),
        root_cause_analysis=RootCauseAnalysis(
            ranked_causes=[RankedCause("CLAIM_UNFOUNDED_BY_BUYER", 1)],
            responsible_parties=[ResponsibleParty(PartyType.CUSTOMER, "cust_001")],
        ),
        evidence_refs=evidence_refs or [_make_valid_evidence_ref(1)],
        data_conflicts=data_conflicts or [],
        financial_resolution=FinancialResolution(
            currency=CURRENCY_BRL,
            recommended_refund_brl=refund_amount,
            refund_lines=refund_lines or [],
        ),
        resolution_actions=resolution_actions or ["CLOSE_CLAIM_REJECTED"],
        claim_assessments=claim_assessments,
        schema_version=OUTPUT_SCHEMA_VERSION,
    )


# ==============================================================================
# 1. VALID MINIMAL & FULL OUTPUT SCHEMA VALIDATION
# ==============================================================================


def test_valid_minimal_output_conforms_to_schema(contracts: Contracts) -> None:
    """A minimal valid L3AOutputV2 must pass both validate_invariants and contracts.validate_output."""
    ref = _make_valid_evidence_ref(10)
    output = _make_base_output(
        status=CaseStatus.NO_ACTION,
        refund_amount=0.0,
        refund_lines=[],
        evidence_refs=[ref],
        resolution_actions=["NO_FURTHER_ACTION_NEEDED"],
    )

    violations = output.validate_invariants(consumed_refs={ref})
    assert violations == [], f"Unexpected invariant violations: {violations}"

    output_dict = output.to_dict()
    contracts.validate_output(output_dict, "minimal_valid_test")
    assert output_dict["schema_version"] == OUTPUT_SCHEMA_VERSION
    assert output_dict["case_id"] == "CASE_M1_TEST_001"
    assert "claim_assessments" not in output_dict  # omitted when None/empty


def test_valid_full_output_conforms_to_schema(contracts: Contracts) -> None:
    """A fully populated L3AOutputV2 with all optional fields and arrays passes schema validation."""
    ref1 = _make_valid_evidence_ref(1)
    ref2 = _make_valid_evidence_ref(2)
    ref3 = _make_valid_evidence_ref(3)

    refund_lines = [
        RefundLine("ITEM_PRICE_REFUND", 150.25, "seller_999"),
        RefundLine("SHIPPING_FEE_REFUND", 25.50, "logistics_partner"),
    ]
    total_refund = 175.75

    output = _make_base_output(
        case_id="CASE_FULL_002",
        status=CaseStatus.ACTION_REQUIRED,
        primary_issue=PrimaryIssue.CANCELED_ORDER_PAID,
        confidence=0.9999,
        refund_amount=total_refund,
        refund_lines=refund_lines,
        evidence_refs=[ref1, ref2, ref3],
        resolution_actions=["APPROVE_FULL_REFUND", "PENALIZE_SELLER"],
        claim_assessments=[
            ClaimAssessment("claim_01", ClaimVerdict.SUPPORTED, 0.98, [ref1]),
            ClaimAssessment("claim_02", ClaimVerdict.PARTIALLY_SUPPORTED, 0.75, [ref2]),
        ],
        data_conflicts=[
            DataConflict(
                field="delivery_timestamp",
                sources=["mcp_carrier_db", "mcp_customer_db"],
                selected_source="mcp_carrier_db",
                resolution_code="PREFER_CARRIER_TELEMETRY",
            )
        ],
    )

    consumed = {ref1, ref2, ref3}
    violations = output.validate_invariants(consumed_refs=consumed)
    assert violations == [], f"Unexpected violations: {violations}"

    output_dict = output.to_dict()
    contracts.validate_output(output_dict, "full_valid_test")
    assert len(output_dict["claim_assessments"]) == 2
    assert len(output_dict["data_conflicts"]) == 1
    assert output_dict["financial_resolution"]["recommended_refund_brl"] == 175.75
    assert len(output_dict["financial_resolution"]["refund_lines"]) == 2


# ==============================================================================
# 2. STATUS 'no_action' INVARIANT CHECKS
# ==============================================================================


def test_status_no_action_with_positive_refund_rejected() -> None:
    """When status is no_action, recommended_refund_brl > 0 must be flagged by validate_invariants."""
    output = _make_base_output(
        status=CaseStatus.NO_ACTION,
        refund_amount=50.0,
        refund_lines=[],
    )
    violations = output.validate_invariants()
    assert any("no_action nhưng recommended_refund_brl = 50.0" in v for v in violations)


def test_status_no_action_with_non_empty_refund_lines_rejected() -> None:
    """When status is no_action, non-empty refund_lines must be flagged even if total refund is 0."""
    output = _make_base_output(
        status=CaseStatus.NO_ACTION,
        refund_amount=0.0,
        refund_lines=[RefundLine("COURTESY_CREDIT", 0.0, None)],
    )
    violations = output.validate_invariants()
    assert any("no_action nhưng refund_lines không rỗng" in v for v in violations)


# ==============================================================================
# 3. STATUS 'action_required' ARITHMETIC INVARIANT CHECKS
# ==============================================================================


def test_status_action_required_mismatching_refund_sum_rejected() -> None:
    """When status is action_required, recommended_refund_brl != sum(lines) must be flagged."""
    output = _make_base_output(
        status=CaseStatus.ACTION_REQUIRED,
        refund_amount=100.0,
        refund_lines=[
            RefundLine("ITEM_REFUND", 60.0, "item_1"),
            RefundLine("FREIGHT_REFUND", 30.0, "item_1"),  # total 90 != 100
        ],
    )
    violations = output.validate_invariants()
    assert any("Tổng tiền hoàn (100.0) không khớp tổng refund_lines (90.0)" in v for v in violations)
    assert not output.financial_resolution.verify_arithmetic_consistency()


def test_status_action_required_matching_refund_sum_accepted() -> None:
    """When status is action_required, matching sum passes invariant check."""
    output = _make_base_output(
        status=CaseStatus.ACTION_REQUIRED,
        refund_amount=90.0,
        refund_lines=[
            RefundLine("ITEM_REFUND", 60.0, "item_1"),
            RefundLine("FREIGHT_REFUND", 30.0, "item_1"),
        ],
    )
    violations = output.validate_invariants()
    assert violations == []
    assert output.financial_resolution.verify_arithmetic_consistency()


# ==============================================================================
# 4. EVIDENCE REFS PROVENANCE & SANITIZATION
# ==============================================================================


def test_unprovenanced_evidence_refs_rejected() -> None:
    """Evidence refs not in consumed_refs must be flagged by validate_invariants."""
    ref_consumed = _make_valid_evidence_ref(1)
    ref_hallucinated = _make_valid_evidence_ref(99)

    output = _make_base_output(
        evidence_refs=[ref_consumed, ref_hallucinated],
    )
    violations = output.validate_invariants(consumed_refs={ref_consumed})
    assert any("không có nguồn gốc trong MCP Gateway" in v for v in violations)
    assert ref_hallucinated in violations[0]


def test_malformed_evidence_ref_discarded_by_to_dict(contracts: Contracts) -> None:
    """Evidence refs that do not match ^ev_[A-Za-z0-9_-]{20,96}$ are stripped in to_dict()."""
    valid_ref = _make_valid_evidence_ref(1)
    malformed_ref_short = "ev_short"
    malformed_ref_prefix = "bad_prefix_12345678901234567890"

    output = _make_base_output(
        evidence_refs=[valid_ref, malformed_ref_short, malformed_ref_prefix],
    )
    d = output.to_dict()
    assert d["evidence_refs"] == [valid_ref]
    contracts.validate_output(d, "sanitized_evidence_refs")


def test_duplicate_evidence_refs_deduplicated_by_to_dict(contracts: Contracts) -> None:
    """Duplicate evidence refs are deduplicated in to_dict() preserving uniqueItems contract."""
    ref = _make_valid_evidence_ref(1)
    output = _make_base_output(
        evidence_refs=[ref, ref, ref],
    )
    d = output.to_dict()
    assert d["evidence_refs"] == [ref]
    contracts.validate_output(d, "deduplicated_evidence_refs")


def test_evidence_refs_capped_at_max_30(contracts: Contracts) -> None:
    """More than 30 evidence_refs are capped to exactly 30 in to_dict()."""
    refs = [_make_valid_evidence_ref(i) for i in range(45)]
    output = _make_base_output(evidence_refs=refs)
    d = output.to_dict()
    assert len(d["evidence_refs"]) == 30
    contracts.validate_output(d, "capped_evidence_refs")


# ==============================================================================
# 5. RESOLUTION ACTIONS DEDUPLICATION & LENGTH LIMITS
# ==============================================================================


def test_resolution_actions_duplicate_flagged_by_invariants() -> None:
    """Duplicate resolution actions are flagged by validate_invariants."""
    output = _make_base_output(
        resolution_actions=["APPROVE_REFUND", "APPROVE_REFUND"],
    )
    violations = output.validate_invariants()
    assert any("resolution_actions chứa phần tử trùng lặp" in v for v in violations)


def test_resolution_actions_excess_length_flagged_by_invariants() -> None:
    """More than 8 resolution actions are flagged by validate_invariants."""
    actions = [f"ACTION_{i}" for i in range(10)]
    output = _make_base_output(resolution_actions=actions)
    violations = output.validate_invariants()
    assert any("resolution_actions vượt quá giới hạn 8 phần tử" in v for v in violations)


def test_resolution_actions_cleaned_and_capped_by_to_dict(contracts: Contracts) -> None:
    """to_dict() deduplicates and caps resolution_actions to 8 items, truncating each to 80 chars."""
    raw_actions = [f"ACTION_{i}_" + ("X" * 100) for i in range(12)] + ["ACTION_0_" + ("X" * 100)]
    output = _make_base_output(resolution_actions=raw_actions)
    d = output.to_dict()
    assert len(d["resolution_actions"]) == 8
    assert all(len(act) <= 80 for act in d["resolution_actions"])
    assert len(d["resolution_actions"]) == len(set(d["resolution_actions"]))
    contracts.validate_output(d, "sanitized_resolution_actions")


# ==============================================================================
# 6. AFFECTED ENTITIES EDGE CONDITIONS
# ==============================================================================


def test_affected_entities_empty_arrays_valid(contracts: Contracts) -> None:
    """AffectedEntities with all empty arrays produces schema-valid output."""
    output = _make_base_output()
    output.affected_entities = AffectedEntities([], [], [], [], [])
    d = output.to_dict()
    for key in ("order_ids", "item_ids", "seller_ids", "payment_references", "shipment_ids"):
        assert d["affected_entities"][key] == []
    contracts.validate_output(d, "empty_entities_test")


def test_affected_entities_deduplication_and_cap_20(contracts: Contracts) -> None:
    """AffectedEntities deduplicates, ignores empty strings, and caps at 20 items."""
    raw_order_ids = [f"ord_{i}" for i in range(25)] + ["ord_0", "", "   "]
    entities = AffectedEntities(order_ids=raw_order_ids)
    d_ent = entities.to_dict()
    assert len(d_ent["order_ids"]) == 20
    assert len(set(d_ent["order_ids"])) == 20
    assert "" not in d_ent["order_ids"]


# ==============================================================================
# 7. BOUNDARY FLOAT VALUES & PRECISION
# ==============================================================================


def test_confidence_boundary_clamping_and_rounding(contracts: Contracts) -> None:
    """Confidence is clamped to [0.0, 1.0] and rounded to 4 decimals."""
    # Test lower bound
    a_low = Assessment(PrimaryIssue.UNSUPPORTED_CLAIM, CaseStatus.NO_ACTION, -0.5)
    assert a_low.confidence == 0.0

    # Test upper bound
    a_high = Assessment(PrimaryIssue.UNSUPPORTED_CLAIM, CaseStatus.NO_ACTION, 1.8)
    assert a_high.confidence == 1.0

    # Test rounding
    a_round = Assessment(PrimaryIssue.UNSUPPORTED_CLAIM, CaseStatus.NO_ACTION, 0.123456)
    assert a_round.to_dict()["confidence"] == 0.1235

    output = _make_base_output()
    output.assessment = a_round
    contracts.validate_output(output.to_dict(), "confidence_boundary")


def test_refund_amounts_clamped_and_rounded() -> None:
    """RefundLine amount_brl and FinancialResolution recommended_refund_brl clamp to >= 0 and round to 2 decimals."""
    line_neg = RefundLine("REASON", -50.0, None)
    assert line_neg.amount_brl == 0.0

    line_float = RefundLine("REASON", 12.3456, None)
    assert line_float.amount_brl == 12.35

    fin_neg = FinancialResolution(recommended_refund_brl=-10.0)
    assert fin_neg.recommended_refund_brl == 0.0

    fin_float = FinancialResolution(recommended_refund_brl=99.999)
    assert fin_float.recommended_refund_brl == 100.0


def test_floating_point_precision_in_arithmetic_consistency() -> None:
    """IEEE 754 precision issues like 0.1 + 0.2 != 0.3 do not cause false invariant violations."""
    # 0.1 + 0.2 in float is 0.30000000000000004
    line1 = RefundLine("ITEM", 0.1, None)
    line2 = RefundLine("ITEM", 0.2, None)
    fin = FinancialResolution(
        currency=CURRENCY_BRL,
        recommended_refund_brl=0.3,
        refund_lines=[line1, line2],
    )
    assert fin.verify_arithmetic_consistency()

    output = _make_base_output(
        status=CaseStatus.ACTION_REQUIRED,
        refund_amount=0.3,
        refund_lines=[line1, line2],
    )
    violations = output.validate_invariants()
    assert violations == []


# ==============================================================================
# 8. CASE ID & ENUM VALIDATION
# ==============================================================================


def test_invalid_case_id_pattern_flagged_by_invariants() -> None:
    """Case IDs that do not match ^[A-Z0-9][A-Z0-9_-]{2,63}$ are flagged."""
    invalid_ids = ["", "ab", "-invalid", "case_lower_is_not_allowed_first_char"]
    for cid in invalid_ids:
        output = _make_base_output(case_id=cid)
        violations = output.validate_invariants()
        assert any("case_id không khớp định dạng chuẩn" in v for v in violations)


def test_case_input_from_dict_rejects_invalid_case_id() -> None:
    """CaseInput.from_dict raises ValueError on invalid case_id."""
    with pytest.raises(ValueError, match="case_id không hợp lệ"):
        CaseInput.from_dict({"case_id": "bad!"})


# ==============================================================================
# 9. DATA CONFLICTS SCHEMA INVARIANTS & ADVERSARIAL EDGE CASE
# ==============================================================================


def test_data_conflict_minimum_two_sources_enforced(contracts: Contracts) -> None:
    """DataConflict sources requires minItems: 2 in JSON Schema."""
    valid_conflict = DataConflict(
        field="payment_status",
        sources=["order_service", "payment_gateway"],
        selected_source="payment_gateway",
        resolution_code="PREFER_PAYMENT_GATEWAY",
    )
    output = _make_base_output(data_conflicts=[valid_conflict])
    d = output.to_dict()
    assert len(d["data_conflicts"]) == 1
    contracts.validate_output(d, "valid_data_conflict")


def test_data_conflict_with_single_source_dropped_by_to_dict(contracts: Contracts) -> None:
    """DataConflict with len(sources) < 2 is dropped by to_dict() to prevent schema violation."""
    invalid_conflict = DataConflict(
        field="payment_status",
        sources=["only_one_source"],
        selected_source="only_one_source",
        resolution_code="NO_CONFLICT",
    )
    output = _make_base_output(data_conflicts=[invalid_conflict])
    d = output.to_dict()
    assert d["data_conflicts"] == []
    contracts.validate_output(d, "dropped_invalid_conflict")


# ==============================================================================
# 10. STATE ACCUMULATION & PROVENANCE BLACKBOARD
# ==============================================================================


def test_case_investigation_state_provenance_tracking() -> None:
    """CaseInvestigationState records valid consumed evidence and validates provenance."""
    case_input = CaseInput(
        case_id="CASE_STATE_001",
        opened_at="2026-09-25T11:00:00Z",
        customer_request=CustomerRequest(
            language="vi",
            message="Don hang bi huy nhung bi tru tien",
            claimed_order_id="ord_abc_123",
            claims=(CustomerClaim("claim_1", "canceled_order_paid"),),
        ),
    )
    state = CaseInvestigationState(case_input=case_input)

    ref1 = _make_valid_evidence_ref(1)
    ref2 = _make_valid_evidence_ref(2)
    state.record_consumed_evidence("order", ref1, {"status": "canceled"})
    state.record_consumed_evidence("payment", ref2, {"total_paid": 120.0})

    assert state.is_evidence_provenanced([ref1, ref2])
    assert not state.is_evidence_provenanced([ref1, _make_valid_evidence_ref(99)])

    # Invalid evidence_ref format rejected immediately
    with pytest.raises(ValueError, match="evidence_ref không đúng định dạng"):
        state.record_consumed_evidence("order", "malformed_ref", {})
