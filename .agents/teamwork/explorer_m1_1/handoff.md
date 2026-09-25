# Handoff Report: Explorer M1.1 (Data Models & State Architecture)

**Working Directory**: `.agents/teamwork/explorer_m1_1`  
**Target Milestone**: M1 (Feature 3: Core Data & State Models — `src/student_agent/models.py`)  
**Date/Timestamp**: 2026-09-25T04:25:00Z  

---

## 1. Observation

### 1.1 Direct Schema Analysis
1. **`contracts/schemas/l3a-output-v2.schema.json`**:
   - Lines 7–11: Requires `schema_version` (const `"day09-l3a-output-v2"`), `case_id` (`^[A-Z0-9][A-Z0-9_-]{2,63}$`), `assessment`, `affected_entities`, `root_cause_analysis`, `evidence_refs`, `data_conflicts`, `financial_resolution`, `resolution_actions`.
   - Lines 32–39: `primary_issue` enum values: `"canceled_order_paid"`, `"unavailable_order_paid"`, `"late_delivery_seller"`, `"late_delivery_logistics"`, `"valid_split_payment"`, `"payment_mismatch"`, `"duplicate_charge"`, `"refund_pending"`, `"refund_failed"`, `"unsupported_claim"`, `"insufficient_evidence"`.
   - Line 45: `case_status` enum values: `"action_required"`, `"no_action"`, `"needs_investigation"`.
   - Lines 50–58: `affected_entities` required keys: `order_ids`, `item_ids`, `seller_ids`, `payment_references`, `shipment_ids`. Each is an array with `maxItems: 20`, `uniqueItems: true`.
   - Lines 64–73: `claim_assessments` items: `claim_id` (str, 1..64), `verdict` (`"supported"`, `"unsupported"`, `"partially_supported"`, `"insufficient_evidence"`), `confidence` (0..1), `evidence_refs` (array of `^ev_[A-Za-z0-9_-]{20,96}$`). Maximum 5 items.
   - Lines 74–101: `root_cause_analysis`:
     - `ranked_causes`: array of max 5 items with `cause_code` (`^[A-Z][A-Z0-9_]{2,79}$`) and `rank` (integer 1..5).
     - `responsible_parties`: array of max 5 items with `party_type` (`"seller"`, `"platform"`, `"logistics_provider"`, `"payment_provider"`, `"customer"`, `"unknown"`) and `party_id` (string or null).
   - Lines 102–105: `evidence_refs`: array of max 30 unique strings matching `^ev_[A-Za-z0-9_-]{20,96}$`.
   - Lines 106–115: `data_conflicts`: array of max 5 items with `field`, `sources` (2..5 unique strings), `selected_source` (str or null), `resolution_code`.
   - Lines 116–135: `financial_resolution`: `currency` (`"BRL"`), `recommended_refund_brl` (number >= 0), `refund_lines` (array of max 10 objects with `reason_code`, `amount_brl`, `entity_id`).
   - Lines 26–29: `resolution_actions`: array of max 8 unique strings (1..80 chars).
   - Line 6: `additionalProperties: false` strictly enforced at root and nested objects.

2. **`contracts/schemas/trace-event-v1.schema.json`**:
   - Lines 7–8: Requires `schema_version` (`"day09-trace-event-v1"`), `event_id` (`^evt_[A-Za-z0-9_-]{12,96}$`), `case_id`, `event_type`, `occurred_at`, `actor`.
   - Lines 12–22: Allowed `event_type`: `"case_received"`, `"task_assigned"`, `"tool_result_consumed"`, `"handoff"`, `"policy_decided"`, `"verification_completed"`, `"case_finalized"`.

3. **`contracts/schemas/mcp-evidence-response-v1.schema.json`**:
   - Lines 7–21: Requires `schema_version` (`"day09-mcp-evidence-v1"`), `evidence_ref` (`^ev_[A-Za-z0-9_-]{20,96}$`), `result_hash`, `domain` (one of `"order"`, `"item"`, `"payment"`, `"shipment"`, `"seller"`, `"customer"`, `"product"`, `"refund"`, `"policy"`), `data`.

4. **`contracts/scoring/scoring-policy-v2.json`**:
   - Lines 31: Consistency rule: "Deterministic cross-field checks for status/refund/action, seller responsibility and duplicate actions."
   - Lines 40: Workflow required events: `["case_received", "task_assigned", "handoff", "verification_completed", "case_finalized"]`.
   - Lines 44–51: Hard gates: `case_id_mismatch`, `unscorable_schema`, `missing_required_evidence`, `invalid_evidence_refs`, `unknown_evidence_ref`, `cross_scope_evidence_ref`.

### 1.2 Direct Codebase & Input Observations
1. **Input Case Structure (`inputs/l3a-inputs-v1/inputs/L3A_CASE_001.json`)**:
   ```json
   {
     "case_id": "L3A_CASE_001",
     "opened_at": "2018-01-01T09:00:00-03:00",
     "customer_request": {
       "language": "vi",
       "message": "Đơn hàng có dấu hiệu bất thường sau thanh toán. Hãy xác minh trạng thái, timeline và quyền lợi phù hợp.",
       "claimed_order_id": "e2a03ccf5ea816036608b2d8c3ab8e60",
       "claims": [
         {"claim_id": "claim-001-a", "topic": "canceled_order_paid"},
         {"claim_id": "claim-001-b", "topic": "requested_full_refund"}
       ]
     },
     "policy_version": "EC_POLICY_V1"
   }
   ```
2. **Current State of `src/student_agent/models.py`**:
   - Does not exist yet. Needs to be designed and created as part of Milestone M1.
3. **Architecture Protocol (`PROJECT.md:88-128`)**:
   - Specialist Agents pass `CaseInvestigationState` starting from `Coordinator` through `OrderAgent`, `PaymentAgent`, `ShipmentAgent` to `PolicyAgent` and `VerifierAgent`.
   - Coordinator produces `InvestigationPlan`.
   - Specialists produce `OrderFindings`, `PaymentFindings`, `ShipmentFindings`.
   - Policy produces `PolicyDecision`.
   - Verifier verifies arithmetic consistency (`recommended_refund_brl == sum(lines)`), evidence provenance (`output.evidence_refs ⊆ state.consumed_evidence_refs`), and produces `L3AOutputV2`.

---

## 2. Logic Chain

1. **Premise**: `Contracts.validate_output()` rejects any dictionary containing undeclared fields (`additionalProperties: false`) or violating length/regex constraints.
2. **Premise**: The competition scoring policy imposes a hard gate (0 score) for `unscorable_schema`, `invalid_evidence_refs`, `unknown_evidence_ref`, and penalizes inconsistency by 10%.
3. **Inference (Type Safety & Central Model)**:
   - Defining typed models with automatic sanitization in `.to_dict()` (such as deduplicating `evidence_refs`, slicing lists to max allowed limits, clamping numeric values, and rounding floats to 2 decimal places) ensures that no Specialist Agent or Policy Agent can produce schema-invalid output.
4. **Inference (A2A Handoff & State Accumulation)**:
   - In a multi-agent system, passing unstructured dictionaries between agents leads to field name collisions, lost evidence references, and uncoordinated tool invocations.
   - By creating `CaseInvestigationState` as a Blackboard state model containing explicit slots for each agent (`order_findings`, `payment_findings`, `shipment_findings`, `policy_decision`) and tracking `consumed_evidence_refs` set, every agent can observe prior findings while accumulating evidence with guaranteed provenance.
5. **Inference (Consistency Invariants)**:
   - Cross-field rules must be verified deterministically before formatting the final JSON:
     - If `case_status == "no_action"`, `recommended_refund_brl` must be `0.0` and `refund_lines` must be empty.
     - If `case_status == "action_required"`, `recommended_refund_brl` must equal `sum(line.amount_brl for line in refund_lines)` with zero arithmetic drift.
     - Every ref in `output.evidence_refs` must belong to `state.consumed_evidence_refs`.
6. **Inference (Educational Requirement R4)**:
   - To satisfy Requirement R4, every class, field, and method must have detailed Vietnamese inline comments and docstrings answering:
     - **WHAT**: What entity or concept does this represent?
     - **HOW**: How is it initialized, computed, converted, or sanitized?
     - **WHY**: Why is this design choice necessary for the multi-agent system and competition rules?

---

## 3. Caveats

1. **Read-Only Investigation Role**:
   - In accordance with explorer constraints, no files were modified in `src/student_agent/`. The complete proposed model source code has been authored in `.agents/teamwork/explorer_m1_1/proposed_models.py` ready for the implementer agent.
2. **Standard Library `dataclasses` vs `pydantic`**:
   - While `pydantic` is installed in the active virtual environment as a transitive dependency of `mcp`, the proposed design utilizes Python 3.11's standard library `dataclasses` combined with explicit serialization methods (`.to_dict()` and `.from_dict()`). This ensures 100% portability, zero external overhead, lightning-fast execution, and zero coupling to Pydantic configuration changes.
3. **Server-Side Tool Variations**:
   - Tool names and parameters are discovered dynamically at runtime via `EvidenceGateway.list_tools()`. The models are designed to store domain findings independently of exact tool names.

---

## 4. Conclusion & Complete Class Specification

The data models and state architecture for `src/student_agent/models.py` are fully designed and implemented in `.agents/teamwork/explorer_m1_1/proposed_models.py`.

### 4.1 Architectural Overview & Entity Hierarchy

```text
Input Case (CaseInput)
   ├── customer_request: CustomerRequest
   │      └── claims: tuple[CustomerClaim, ...]
   ▼
Investigation Plan (InvestigationPlan)
   ├── needed_domains: list[str]
   └── assigned_agents: list[str]
   ▼
Blackboard State (CaseInvestigationState)
   ├── order_findings: OrderFindings (OrderItemData)
   ├── payment_findings: PaymentFindings (PaymentLineData)
   ├── shipment_findings: ShipmentFindings
   ├── seller_findings: dict[str, SellerFindings]
   ├── customer_findings: CustomerFindings
   ├── consumed_evidence_refs: set[str] (Audit Trail)
   ├── handoff_history: list[AgentHandoffMessage]
   ▼
Policy Outcome (PolicyDecision)
   ├── assessment: Assessment
   ├── affected_entities: AffectedEntities
   ├── claim_assessments: list[ClaimAssessment]
   ├── root_cause_analysis: RootCauseAnalysis (RankedCause, ResponsibleParty)
   ├── financial_resolution: FinancialResolution (RefundLine)
   ├── resolution_actions: list[str]
   ├── data_conflicts: list[DataConflict]
   ▼
Final Output (L3AOutputV2) -> .to_dict() -> contracts/schemas/l3a-output-v2.schema.json
```

### 4.2 Detailed Class & Signature Inventory

#### 1. Contract Constants & Enums
- `PrimaryIssue(str, Enum)`: 11 values (`canceled_order_paid`, `unavailable_order_paid`, `late_delivery_seller`, `late_delivery_logistics`, `valid_split_payment`, `payment_mismatch`, `duplicate_charge`, `refund_pending`, `refund_failed`, `unsupported_claim`, `insufficient_evidence`).
- `CaseStatus(str, Enum)`: 3 values (`action_required`, `no_action`, `needs_investigation`).
- `ClaimVerdict(str, Enum)`: 4 values (`supported`, `unsupported`, `partially_supported`, `insufficient_evidence`).
- `PartyType(str, Enum)`: 6 values (`seller`, `platform`, `logistics_provider`, `payment_provider`, `customer`, `unknown`).
- `EvidenceDomain(str, Enum)`: 9 values (`order`, `item`, `payment`, `shipment`, `seller`, `customer`, `product`, `refund`, `policy`).
- `TraceEventType(str, Enum)`: 7 values (`case_received`, `task_assigned`, `tool_result_consumed`, `handoff`, `policy_decided`, `verification_completed`, `case_finalized`).
- `AgentRole(str, Enum)`: 6 values (`coordinator`, `order-agent`, `payment-agent`, `shipment-agent`, `policy-agent`, `verifier`).

#### 2. Input Models
- `CustomerClaim`: `claim_id: str`, `topic: str`, `detail: str | None = None`. Classmethod `from_dict(data)`.
- `CustomerRequest`: `language: str`, `message: str`, `claimed_order_id: str`, `claims: tuple[CustomerClaim, ...]`. Classmethod `from_dict(data)`.
- `CaseInput`: `case_id: str`, `opened_at: str`, `customer_request: CustomerRequest`, `policy_version: str = "EC_POLICY_V1"`.
  - Properties: `order_id -> str`, `claim_topics -> list[str]`.
  - Classmethod: `from_dict(data) -> CaseInput`.

#### 3. Coordination & A2A Handoff Models
- `InvestigationPlan`: `case_id: str`, `order_id: str`, `claims: list[CustomerClaim]`, `needed_domains: list[str]`, `assigned_agents: list[str]`, `hypotheses: list[str]`, `strategy_notes: str`.
- `AgentHandoffMessage`: `sender: str`, `receiver: str`, `decision_code: str`, `summary: str`, `new_evidence_refs: list[str]`, `attributes: dict[str, Any]`, `timestamp: str`.

#### 4. Specialist Findings Models
- `OrderItemData`: `order_id: str`, `order_item_id: int | str`, `product_id: str`, `seller_id: str`, `shipping_limit_date: str | None`, `price: float`, `freight_value: float`. Property: `total_value -> float`.
- `OrderFindings`: `order_id: str`, `status: str`, `customer_id: str | None`, `order_purchase_timestamp: str | None`, `order_approved_at: str | None`, `order_delivered_carrier_date: str | None`, `order_delivered_customer_date: str | None`, `order_estimated_delivery_date: str | None`, `items: list[OrderItemData]`, `seller_ids: list[str]`, `item_ids: list[str]`, `total_items_price: float`, `total_freight_value: float`, `total_order_value: float`, `evidence_refs: list[str]`, `raw_data: dict[str, Any]`. Properties: `is_canceled -> bool`, `is_unavailable -> bool`, `is_delivered -> bool`.
- `PaymentLineData`: `order_id: str`, `payment_sequential: int`, `payment_type: str`, `payment_installments: int`, `payment_value: float`, `payment_reference: str | None`.
- `PaymentFindings`: `order_id: str`, `payment_lines: list[PaymentLineData]`, `payment_types: list[str]`, `payment_references: list[str]`, `total_paid: float`, `is_split_payment: bool`, `has_duplicate_charge: bool`, `payment_mismatch: bool`, `expected_order_value: float`, `difference_amount: float`, `refund_status: str | None`, `refund_amount_processed: float`, `evidence_refs: list[str]`, `raw_data: dict[str, Any]`.
- `ShipmentFindings`: `order_id: str`, `shipment_ids: list[str]`, `carrier_partner: str | None`, `shipping_limit_date: str | None`, `delivered_carrier_date: str | None`, `delivered_customer_date: str | None`, `estimated_delivery_date: str | None`, `is_delayed: bool`, `delay_days: float`, `seller_delay: bool`, `seller_delay_days: float`, `carrier_delay: bool`, `carrier_delay_days: float`, `delivery_status: str`, `evidence_refs: list[str]`, `raw_data: dict[str, Any]`.
- `SellerFindings` & `CustomerFindings`: Demographic and address metadata with `evidence_refs`.

#### 5. Policy Decision Models
- `Assessment`: `primary_issue: PrimaryIssue | str`, `case_status: CaseStatus | str`, `confidence: float`. Method: `to_dict() -> dict[str, Any]`.
- `AffectedEntities`: `order_ids: list[str]`, `item_ids: list[str]`, `seller_ids: list[str]`, `payment_references: list[str]`, `shipment_ids: list[str]`. Method: `to_dict() -> dict[str, Any]` (deduplicates, limits to 20 each).
- `ClaimAssessment`: `claim_id: str`, `verdict: ClaimVerdict | str`, `confidence: float`, `evidence_refs: list[str]`. Method: `to_dict() -> dict[str, Any]` (limits to 30 refs).
- `RankedCause`: `cause_code: str`, `rank: int`. Method: `to_dict() -> dict[str, Any]`.
- `ResponsibleParty`: `party_type: PartyType | str`, `party_id: str | None`. Method: `to_dict() -> dict[str, Any]`.
- `RootCauseAnalysis`: `ranked_causes: list[RankedCause]`, `responsible_parties: list[ResponsibleParty]`. Method: `to_dict() -> dict[str, Any]` (limits to 5 each).
- `RefundLine`: `reason_code: str`, `amount_brl: float`, `entity_id: str | None`. Method: `to_dict() -> dict[str, Any]`.
- `FinancialResolution`: `currency: str = "BRL"`, `recommended_refund_brl: float`, `refund_lines: list[RefundLine]`. Methods: `verify_arithmetic_consistency() -> bool`, `to_dict() -> dict[str, Any]`.
- `DataConflict`: `field: str`, `sources: list[str]`, `selected_source: str | None`, `resolution_code: str`. Method: `to_dict() -> dict[str, Any]` (limits to 5 sources).
- `PolicyDecision`: Aggregate container holding `assessment`, `affected_entities`, `root_cause_analysis`, `financial_resolution`, `claim_assessments`, `evidence_refs`, `data_conflicts`, `resolution_actions`.

#### 6. Blackboard State Model
- `CaseInvestigationState`:
  - Fields: `case_input`, `plan`, `order_findings`, `payment_findings`, `shipment_findings`, `seller_findings`, `customer_findings`, `policy_decision`, `final_output`, `consumed_evidence_refs: set[str]`, `evidence_by_domain: dict[str, list[dict]]`, `discovered_tools: list[str]`, `handoff_history: list[AgentHandoffMessage]`, `errors: list[str]`.
  - Methods:
    - `record_consumed_evidence(domain: str, evidence_ref: str, data: dict[str, Any]) -> None`
    - `record_handoff(sender, receiver, decision_code, summary, new_evidence_refs, attributes) -> AgentHandoffMessage`
    - `extract_affected_entities() -> AffectedEntities`
    - `is_evidence_provenanced(refs: list[str]) -> bool`

#### 7. Final Output Model
- `L3AOutputV2`:
  - Fields: `case_id`, `assessment`, `affected_entities`, `root_cause_analysis`, `evidence_refs`, `data_conflicts`, `financial_resolution`, `resolution_actions`, `claim_assessments: list[ClaimAssessment] | None = None`, `schema_version = "day09-l3a-output-v2"`.
  - Classmethod: `from_decision(case_id: str, decision: PolicyDecision) -> L3AOutputV2`.
  - Method: `validate_invariants(consumed_refs: set[str] | None = None) -> list[str]`.
  - Method: `to_dict() -> dict[str, Any]`.

---

## 5. Verification Method

1. **Independent File Inspection**:
   - Inspect `.agents/teamwork/explorer_m1_1/proposed_models.py` directly.
   - Verify that all classes, fields, and method signatures strictly comply with `contracts/schemas/l3a-output-v2.schema.json`.
2. **Schema & Invariant Verification**:
   - Run python code using `Contracts.validate_output()` on an instance of `L3AOutputV2.to_dict()`:
     ```python
     from pathlib import Path
     from student_agent.contracts import Contracts
     from student_agent.models import Assessment, AffectedEntities, FinancialResolution, L3AOutputV2, RootCauseAnalysis
     
     contracts = Contracts(Path("contracts/schemas"))
     sample_output = L3AOutputV2(
         case_id="L3A_CASE_001",
         assessment=Assessment("canceled_order_paid", "action_required", 0.95),
         affected_entities=AffectedEntities(["ord_123"], [], [], [], []),
         root_cause_analysis=RootCauseAnalysis([], []),
         evidence_refs=["ev_123456789012345678901234"],
         data_conflicts=[],
         financial_resolution=FinancialResolution("BRL", 100.0, []),
         resolution_actions=["APPROVE_FULL_REFUND"],
     ).to_dict()
     contracts.validate_output(sample_output, "test_validation")
     ```
3. **Invalidation Conditions**:
   - If `contracts/schemas/l3a-output-v2.schema.json` is modified to alter enum values or field requirements, update the corresponding Enum and dataclass in `models.py`.
