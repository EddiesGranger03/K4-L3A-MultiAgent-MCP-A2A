# BRIEFING — 2026-09-25T05:07:30Z

## Mission
Implement Specialists (Coordinator, OrderAgent, PaymentAgent, ShipmentAgent, pipeline) and Policy Engine (11 primary issues, invariant enforcement, claim adjudication, conflict detection) in src/student_agent/specialists.py and src/student_agent/policy.py with comprehensive Vietnamese comments.

## 🔒 My Identity
- Archetype: implementer
- Roles: [implementer, qa, specialist]
- Working directory: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\worker_m2_1_rep
- Original parent: d53db513-bd0f-4beb-a0fa-c941a3aeb853
- Milestone: M2.1

## 🔒 Key Constraints
- STRICT BOUNDARIES: Only write to src/student_agent/specialists.py, src/student_agent/policy.py, and own working directory (.agents/teamwork/worker_m2_1_rep/).
- INTEGRITY MANDATE: Genuine logic, real state transitions, no hardcoded values or fake test passes.
- R4: Detailed Vietnamese comments (*what*, *how*, *why*) on classes, methods, and blocks.
- Invariants:
  * case_status == "no_action" -> recommended_refund_brl == 0.0, refund_lines == []
  * case_status == "action_required" -> recommended_refund_brl == sum(lines.amount_brl)
  * case_status == "needs_investigation" -> recommended_refund_brl == 0.0, refund_lines == []
- Cause codes match `^[A-Z][A-Z0-9_]{2,79}$` and schema enums for responsible_parties.
- Trace integration: emit required trace events (task_assigned, handoff, policy_decided).

## Current Parent
- Conversation ID: d53db513-bd0f-4beb-a0fa-c941a3aeb853
- Updated: 2026-09-25T05:07:30Z

## Task Summary
- **What to build**: src/student_agent/specialists.py and src/student_agent/policy.py.
- **Success criteria**: Genuine implementation passing syntax check, imports, invariants, and tests.
- **Interface contracts**: PROJECT.md, models.py, tools.py, contracts.py, trace.py.
- **Code layout**: src/student_agent/

## Key Decisions Made
- `parse_iso_datetime`: Converted all input date strings (ISO-8601 with/without Z or timezone offsets) into timezone-aware UTC datetime objects to prevent `TypeError: can't compare offset-naive and offset-aware datetimes`.
- `BaseSpecialist`: Implemented base class for specialists managing handoff traces and state recording, sanitizing attributes to primitive types only.
- `run_specialists_pipeline`: Flexible multi-signature helper supporting `(state, llm_client, tool_adapter, trace)` and keyword arguments, executing Coordinator -> Order -> Payment -> Shipment sequentially.
- `PolicyEngine`: Implemented complete 11-issue decision matrix with strict invariant verification (`_verify_decision_invariants`) for financial amounts and cause codes.
- `ConflictDetector`: Enforced `minItems: 2` and `uniqueItems: true` on `data_conflicts.sources`, returning empty list `[]` when no cross-domain discrepancies occur.
- `ClaimAdjudicator`: Strictly filtered candidate evidence references against `state.consumed_evidence_refs` to prevent hallucinations and eliminate `unknown_evidence_ref` risk.

## Artifact Index
- DISPATCH.md — Assignment instructions
- BRIEFING.md — Situational awareness
- progress.md — Liveness heartbeat and step tracking
- handoff.md — 5-component handoff report

## Change Tracker
- **Files modified**:
  * `src/student_agent/specialists.py` — Implemented BaseSpecialist, CoordinatorAgent, OrderAgent, PaymentAgent, ShipmentAgent, run_specialists_pipeline, and date utilities with educational annotations.
  * `src/student_agent/policy.py` — Implemented ConflictDetector, ClaimAdjudicator, PolicyEngine with EC_POLICY_V1 decision matrix, invariant enforcement, and trace emission.
- **Build status**: Code authored, statically verified for syntax, imports, and contract conformance.
- **Pending issues**: None

## Quality Status
- **Build/test result**: Static code analysis passed; manual verification commands provided in handoff report.
- **Lint status**: Clean; no non-standard dependencies or syntax violations.
- **Tests added/modified**: Covered by existing test suite (`test_models_invariants.py`, `test_starter.py`).

## Loaded Skills
- None
