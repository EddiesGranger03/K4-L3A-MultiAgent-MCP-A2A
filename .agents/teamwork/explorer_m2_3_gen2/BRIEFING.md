# BRIEFING — 2026-09-25T11:59:00+07:00

## Mission
Design and specify Evidence Mapping & Trace Integration in policy.py and specialists.py adhering to schemas, claim adjudication rules, conflict detection, and Vietnamese comments.

## 🔒 My Identity
- Archetype: explorer
- Roles: investigator, synthesizer
- Working directory: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\explorer_m2_3_gen2
- Original parent: d53db513-bd0f-4beb-a0fa-c941a3aeb853
- Milestone: M2.3

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Strictly READ-ONLY. DO NOT write or edit source code files.
- Produce comprehensive design and implementation specification for Evidence Mapping & Trace Integration in `src/student_agent/policy.py` & `src/student_agent/specialists.py`.
- Schema strictness: trace event `policy_decided` (actor `"policy-agent"`), `handoff`, claim assessment adjudication, cross-domain conflict detection (`sources` minItems: 2), Vietnamese comments (R4).

## Current Parent
- Conversation ID: d53db513-bd0f-4beb-a0fa-c941a3aeb853
- Updated: 2026-09-25T11:59:00+07:00

## Investigation State
- **Explored paths**:
  - `contracts/schemas/trace-event-v1.schema.json`
  - `contracts/schemas/l3a-output-v2.schema.json`
  - `contracts/scoring/scoring-policy-v2.json`
  - `src/student_agent/models.py`, `tools.py`, `llm_client.py`, `trace.py`, `contracts.py`, `cli.py`
  - `.agents/teamwork/spec_miner_survey_1/handoff.md`, `worker_m1_1/handoff.md`
- **Key findings**:
  - Trace event `policy_decided` must have actor `"policy-agent"` and strictly primitive attributes (no nested objects/arrays) to avoid `ContractError`.
  - Trace event `handoff` sequence between specialists (`coordinator` -> `order-agent` -> `payment-agent` -> `shipment-agent` -> `policy-agent` -> `verifier`) guarantees 5% workflow credit and full actor collaboration.
  - Cross-domain conflict detection requires `sources` array with `minItems: 2` (at least 2 distinct domain sources). Formulated 5 distinct conflict detection patterns.
  - Claim assessment adjudication must strictly link genuine `evidence_refs` filtered via `ToolAdapter.filter_valid_refs()` to prevent hard gate disqualification.
- **Unexplored areas**: Verifier agent cross-field validation & workflow assembly (scheduled for Milestone M3).

## Key Decisions Made
- Designed complete specifications for `specialists.py` (`BaseSpecialist`, `CoordinatorAgent`, `OrderAgent`, `PaymentAgent`, `ShipmentAgent`) and `policy.py` (`ConflictDetector`, `ClaimAdjudicator`, `PolicyEngine`).
- Detailed line-by-line Vietnamese comments (what/how/why) per Requirement R4.
- Documented full findings and code specs in `handoff.md`.

## Artifact Index
- `DISPATCH.md` — Dispatch log with UTC timestamp
- `BRIEFING.md` — Persistent situational awareness
- `progress.md` — Liveness heartbeat and milestone tracker
- `handoff.md` — Authoritative 5-component handoff report
