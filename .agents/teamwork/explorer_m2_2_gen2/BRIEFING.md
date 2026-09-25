# BRIEFING — 2026-09-25T05:00:15Z

## Mission
Produce a comprehensive design and implementation specification for `src/student_agent/policy.py` covering the 11 primary issues, case_status determination, root cause ranking, financial resolution calculations, and resolution actions according to schema invariants and Vietnamese comments (R4).

## 🔒 My Identity
- Archetype: explorer
- Roles: Policy Engine Explorer, Decision Matrix & Financial Resolution Designer
- Working directory: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\explorer_m2_2_gen2
- Original parent: d53db513-bd0f-4beb-a0fa-c941a3aeb853
- Milestone: M2.2

## 🔒 Key Constraints
- Read-only investigation — do NOT implement or modify source code files
- Design and specify policy engine for src/student_agent/policy.py covering 11 primary issues
- Strict adherence to contracts/scoring-policy-v2.json and contracts/schemas/
- Strict adherence to schema invariants (currency BRL, refund sums, status mappings, root cause codes, Vietnamese comments R4)

## Current Parent
- Conversation ID: d53db513-bd0f-4beb-a0fa-c941a3aeb853
- Updated: not yet

## Investigation State
- **Explored paths**:
  - `contracts/scoring/scoring-policy-v2.json`
  - `contracts/schemas/l3a-output-v2.schema.json`
  - `contracts/schemas/trace-event-v1.schema.json`
  - `contracts/schemas/mcp-evidence-response-v1.schema.json`
  - `src/student_agent/models.py`
  - `src/student_agent/llm_client.py`
  - `src/student_agent/tools.py`
  - `src/student_agent/trace.py`
  - `src/student_agent/cases.py`
  - `tests/test_models_invariants.py`
  - `tests/test_m1_challenger_stress.py`
  - `inputs/l3a-inputs-v1/inputs/L3A_CASE_001.json` - `010.json`
- **Key findings**:
  - Complete mapping of 11 primary issues to facts, statuses, root cause codes, responsible parties, financial resolutions, and actions.
  - Verification of all schema invariants: no_action requires refund=0 and empty lines; action_required requires refund == sum(lines).
  - Trace event `policy_decided` requirements and payload attributes.
  - Requirement R4 compliance via structured Vietnamese docstrings (WHAT, HOW, WHY).
- **Unexplored areas**: None for policy engine scope. Ready for handoff synthesis.

## Key Decisions Made
- Standardized all 11 primary issues with deterministic fallback rules and exact financial formulas.
- Validated all cause codes against regex `^[A-Z][A-Z0-9_]{2,79}$`.
- Ensured zero-leak and provenance guarantees by binding output evidence refs strictly to `state.consumed_evidence_refs`.

## Artifact Index
- DISPATCH.md — Recorded dispatch instructions
- BRIEFING.md — Situational awareness working memory
- progress.md — Liveness heartbeat
- handoff.md — Final comprehensive design specification
