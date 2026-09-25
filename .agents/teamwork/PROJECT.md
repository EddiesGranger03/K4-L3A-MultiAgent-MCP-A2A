# Project: K4-L3A Multi-Agent E-Commerce Complaint Investigation System

## Architecture
A modular, Agent-to-Agent (A2A) coordinated pipeline integrating an MCP Gateway for evidence retrieval and NVIDIA Nemotron 8B for reasoning and safety guardrails.

```
                          [ Input Case ]
                                │
                                ▼
                       [ Coordinator Agent ]
                     (emits: task_assigned)
                                │
       ┌────────────────────────┼────────────────────────┐
       ▼                        ▼                        ▼
 [ Order Agent ]        [ Payment Agent ]       [ Shipment Agent ]
  (tools: order, item)   (tools: payment, refund) (tools: shipment, carrier)
       │                        │                        │
       └────────────────────────┼────────────────────────┘
                                │
                                ▼
                        [ Policy Agent ]
                     (evaluates EC_POLICY_V1)
                     (emits: policy_decided)
                                │
                                ▼
                       [ Verifier Agent ]
                    (cross-field consistency,
                     provenance audit, schema check)
                  (emits: verification_completed)
                                │
                                ▼
                        [ Final Output ]
```

### Trace Lifecycle Sequence (Per Case)
1. `case_received` (emitted by `cli.py` before `solve_case`)
2. `task_assigned` (emitted by `Coordinator` when assigning specialists)
3. `tool_result_consumed` (emitted by specialist agents upon consuming MCP evidence, recording `evidence_refs`)
4. `handoff` (emitted during specialist-to-specialist and specialist-to-policy transitions)
5. `policy_decided` (emitted by `Policy Agent` upon resolving primary issue & refund lines)
6. `verification_completed` (emitted by `Verifier` after verifying schema invariants & provenance)
7. `case_finalized` (emitted by `cli.py` after `solve_case` output written)

### Code Layout
- `src/student_agent/workflow.py`: Main entry point `solve_case(case, gateway, trace)`.
- `src/student_agent/models.py`: Internal state dataclasses, specialist results, and context models.
- `src/student_agent/llm_client.py`: Async NVIDIA NIM client calling `Llama 3.1 Nemotron Safety Guard 8B v3` via `httpx2`.
- `src/student_agent/tools.py`: Dynamic MCP Tool Discovery, tool invocation wrapper, and evidence tracker.
- `src/student_agent/specialists.py`: Coordinator, OrderAgent, PaymentAgent, ShipmentAgent implementations.
- `src/student_agent/policy.py`: PolicyAgent implementing `EC_POLICY_V1` decision matrix for all 11 primary issues.
- `src/student_agent/verifier.py`: Verifier agent for consistency invariants, provenance check, and output assembly.
- `tests/`: Unit tests and offline mock fixtures.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | NVIDIA LLM Client | Async client using `httpx2` to call NVIDIA Nemotron Safety Guard 8B API | M1 | ORIGINAL_REQUEST §R2 |
| 2 | Dynamic Tool Adapter & Evidence Tracker | Discovers MCP tools dynamically via `list_tools`, wraps calls with `case_id`, tracks genuine `evidence_refs` | M1 | ORIGINAL_REQUEST §R3 |
| 3 | Core Data & State Models | Internal representation of case context, specialist findings, and evidence references | M1 | ARCHITECTURE.md |
| 4 | Coordinator Specialist | Parses complaint, extracts claimed order/claims, assigns investigation tasks via `task_assigned` | M2 | ORIGINAL_REQUEST §R1 |
| 5 | Order Specialist | Queries order/items domain, verifies order status, items, seller IDs, emits `tool_result_consumed` & `handoff` | M2 | ORIGINAL_REQUEST §R1, R3 |
| 6 | Payment Specialist | Queries payment/refund domain, validates payment method, split payments, amounts, emits trace & `handoff` | M2 | ORIGINAL_REQUEST §R1, R3 |
| 7 | Shipment Specialist | Queries shipment domain, calculates delivery dates vs estimates, attributes seller vs carrier delays | M2 | ORIGINAL_REQUEST §R1, R3 |
| 8 | Policy Agent (`EC_POLICY_V1`) | Evaluates 11 primary issues, root cause codes, responsible parties, and refund amounts/lines | M2 | contracts/scoring-policy-v2.json |
| 9 | Verifier Agent | Cross-field consistency verification, arithmetic check (`refund_brl` == sum lines), provenance audit | M3 | contracts/scoring-policy-v2.json |
| 10 | Workflow Pipeline Assembly | Integrates all agents into `solve_case` in `workflow.py` with trace emission and error recovery | M3 | ORIGINAL_REQUEST §R1, R3 |
| 11 | Educational Code Comments | Comprehensive Vietnamese comments (*what*, *how*, *why*) on all classes, functions, and steps | M3 | ORIGINAL_REQUEST §R4 |
| 12 | Offline Unit Test Suite & Fixtures | Synthetic mock `EvidenceGateway` and tests for agents, policy, and workflow (`pytest -q`) | E2E/M4 | ORIGINAL_REQUEST Verification |
| 13 | Full 100-Case Validation & Hardening | Passes `day09 run`, `day09 validate`, and zero secret leaks or hard gate violations | M4 | ORIGINAL_REQUEST Acceptance |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Foundation: LLM, Tools & Models | `models.py`, `llm_client.py`, `tools.py` | none | DONE |
| M2 | Specialist Agents & Policy Engine | `specialists.py`, `policy.py` | M1 | PLANNED |
| M3 | Verifier, Workflow Integration & Docs | `verifier.py`, `workflow.py`, Vietnamese annotations | M1, M2 | PLANNED |
| M4 | Final Milestone: Test Pass & Hardening | `tests/`, `pytest -q`, `day09 run`, `day09 validate` | M1, M2, M3, E2E | PLANNED |
| E2E | E2E Testing Track | Test infra, mock fixtures, 4 tiers of test cases | none | PLANNED |

## Interface Contracts

### 1. `llm_client.py` ↔ Specialist Agents
- Class: `NvidiaLLMClient(api_key: str, model: str = "nvidia/llama-3.1-nemotron-safety-guard-8b-v3")`
- Method: `async def analyze_intent(self, text: str, claims: list[dict]) -> dict[str, Any]`
- Method: `async def evaluate_safety(self, text: str) -> dict[str, Any]`
- Returns: structured dict with extracted entities, sentiment, risk category, and reasoning.

### 2. `tools.py` ↔ Specialist Agents
- Class: `ToolAdapter(gateway: EvidenceGateway, trace: TraceWriter, case_id: str)`
- Method: `async def call(self, tool_name: str, actor: str, **arguments) -> dict[str, Any]`
- Emits: `trace.emit(case_id=self.case_id, event_type="tool_result_consumed", actor=actor, tool_name=tool_name, evidence_refs=[envelope["evidence_ref"]])`
- Tracks: `self.consumed_evidence_refs: set[str]` and `self.evidence_by_domain: dict[str, list[dict]]`.
- Returns: unpacked `data` dict from the evidence envelope along with `evidence_ref`.

### 3. `specialists.py` ↔ `policy.py`
- Protocol: `CaseInvestigationState` passed from Coordinator through specialists.
- Coordinator output: `InvestigationPlan(order_id, claims, needed_domains)`
- OrderAgent output: `OrderFindings(status, order_date, items, seller_ids, evidence_refs)`
- PaymentAgent output: `PaymentFindings(payment_types, total_paid, refund_status, evidence_refs)`
- ShipmentAgent output: `ShipmentFindings(delivery_date, estimated_date, carrier_delay, seller_delay, evidence_refs)`
- Trace events emitted: `task_assigned` (by coordinator), `handoff` (between agents).

### 4. `policy.py` ↔ `verifier.py`
- Class: `PolicyEngine`
- Method: `evaluate(state: CaseInvestigationState) -> PolicyDecision`
- Emits: `trace.emit(case_id=case_id, event_type="policy_decided", actor="policy-agent", ...)`
- PolicyDecision attributes:
  - `primary_issue`: one of 11 valid enums.
  - `case_status`: `"action_required" | "no_action" | "needs_investigation"`.
  - `confidence`: float `[0.0, 1.0]`.
  - `ranked_causes`: list of `{ "cause_code": str, "rank": int }`.
  - `responsible_parties`: list of `{ "party_type": str, "party_id": str | None }`.
  - `financial_resolution`: `{ "currency": "BRL", "recommended_refund_brl": float, "refund_lines": [...] }`.
  - `claim_assessments`: list of `{ "claim_id": str, "verdict": str, "confidence": float, "evidence_refs": [...] }`.
  - `resolution_actions`: list of unique strings.

### 5. `verifier.py` ↔ `workflow.py`
- Class: `VerifierAgent`
- Method: `verify_and_assemble(state: CaseInvestigationState, decision: PolicyDecision) -> dict[str, Any]`
- Invariant Checks:
  - If `case_status == "no_action"`, `recommended_refund_brl == 0` and `refund_lines == []`.
  - If `case_status == "action_required"`, `recommended_refund_brl == sum(line["amount_brl"])`.
  - Provenance: all `evidence_refs` in output must be a subset of `state.tool_adapter.consumed_evidence_refs`.
  - No secret key strings.
  - Validates output against `Contracts.validate_output`.
- Emits: `trace.emit(case_id=case_id, event_type="verification_completed", actor="verifier")`
- Returns: validated dict conforming to `day09-l3a-output-v2`.
