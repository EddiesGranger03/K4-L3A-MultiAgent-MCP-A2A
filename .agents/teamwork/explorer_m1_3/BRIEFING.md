# BRIEFING — 2026-09-25T11:21:00+07:00

## Mission
Produce the exact architecture, class design, and implementation specification for `src/student_agent/tools.py` (ToolAdapter, dynamic discovery, safe call wrapper, evidence tracking, trace event emission, anti-hallucination, Vietnamese inline comments).

## 🔒 My Identity
- Archetype: explorer
- Roles: investigation, synthesis
- Working directory: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\explorer_m1_3
- Original parent: e6841c53-abd8-43b4-af23-1e1bdcf454bc
- Milestone: M1.3 (Tool Adapter & Evidence Tracker)

## 🔒 Key Constraints
- Read-only investigation — do NOT implement in src/
- Target: Detailed design and implementation specification of `src/student_agent/tools.py`
- Strict compliance with PROJECT.md, ORIGINAL_REQUEST.md, and benchmark requirements
- Must include Vietnamese inline comments (*what*, *how*, *why*) for all methods/classes (R4)
- Anti-hallucination: only genuine `evidence_ref` returned by gateway tracked/stored
- Emit `tool_result_consumed` trace event immediately upon each successful tool call with exact `evidence_refs=[envelope["evidence_ref"]]` and `tool_name`

## Current Parent
- Conversation ID: e6841c53-abd8-43b4-af23-1e1bdcf454bc
- Updated: not yet

## Investigation State
- **Explored paths**:
  - `src/student_agent/mcp_gateway.py` (lines 15-57)
  - `src/student_agent/trace.py` (lines 12-51)
  - `src/student_agent/contracts.py` (lines 17-54)
  - `src/student_agent/cli.py` (lines 22-61)
  - `src/student_agent/workflow.py` (lines 9-19)
  - `contracts/schemas/mcp-evidence-response-v1.schema.json`
  - `contracts/schemas/trace-event-v1.schema.json`
  - `contracts/schemas/l3a-output-v2.schema.json`
  - `contracts/scoring/scoring-policy-v2.json`
  - `README.md`, `ARCHITECTURE.md`, `PROJECT.md`, `ORIGINAL_REQUEST.md`
  - Survey handoffs: `spec_miner_survey_1`, `explorer_survey_1`, `explorer_survey_2`
- **Key findings**:
  - `EvidenceGateway.call` validates `mcp-evidence-response-v1.schema.json` and returns envelope dict containing `evidence_ref`, `result_hash`, `domain`, `data`, `warnings`.
  - `TraceWriter.emit` validates `trace-event-v1.schema.json`. For `tool_result_consumed`, `tool_name` and `evidence_refs` are required.
  - Zero-tolerance scoring hard gates: `unknown_evidence_ref` (0 points), `cross_scope_evidence_ref` (0 points), `invalid_evidence_refs` (0 points).
  - Provenance (15%) and Workflow (5%) require 100% of submitted evidence refs to be verified against trace logs and MCP audit tables.
  - Complete architecture of `ToolAdapter` and `ToolResult` designed with educational Vietnamese annotations.
- **Unexplored areas**: Implementation and unit testing (delegated to M1 implementation and M4/E2E test tracks).

## Key Decisions Made
- `ToolResult` supports both object attribute access (`result.data`, `result.evidence_ref`) and dictionary subscripting (`result["data"]`, `result["evidence_ref"]`).
- `ToolAdapter` encapsulates `_consumed_evidence_refs: set[str]` with strictly append-only behavior tied to successful gateway calls; external access is read-only via copy.
- Provides `filter_valid_refs()` and `is_valid_consumed_ref()` helper methods for Verifier and Specialist agents to eliminate LLM hallucinations.
- Implements bounded retry logic (2 retries with exponential backoff) for transient transport errors.
- Real-time emission of `tool_result_consumed` event immediately upon unpacking evidence.

## Artifact Index
- BRIEFING.md — Persistent working memory
- DISPATCH.md — Task dispatch log
- progress.md — Liveness heartbeat & task tracking
- handoff.md — Final handoff report
