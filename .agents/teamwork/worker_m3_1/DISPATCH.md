## 2026-09-25T05:21:30Z
You are Worker M3.1 (Core Integration & Pipeline Worker).
Your working directory is: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\worker_m3_1

Read the authoritative requirements:
- ORIGINAL_REQUEST.md: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\ORIGINAL_REQUEST.md
- PROJECT.md: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\PROJECT.md
- Explorer M3.1 Handoff: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\explorer_m3_1\handoff.md
- Explorer M3.2 Handoff: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\explorer_m3_2\handoff.md
- Explorer M3.3 Handoff: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\explorer_m3_3\handoff.md

FILE WRITE OWNERSHIP:
You have EXCLUSIVE write ownership of:
- `src/student_agent/llm_client.py`
- `src/student_agent/verifier.py`
- `src/student_agent/workflow.py`
You may also add new test files under `tests/` if needed to verify your implementation.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Tasks to implement:
1. `src/student_agent/llm_client.py`:
   - Update default constants:
     - `DEFAULT_NVIDIA_MODEL = "deepseek-ai/deepseek-v4.1-flash"`
     - `DEFAULT_NVIDIA_API_KEY = "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"`
   - In `NvidiaLLMClient.__init__`: normalize API key by removing `"Bearer "` prefix if present (`if resolved_key.startswith("Bearer "): resolved_key = resolved_key[7:].strip()`) so Authorization header is strictly `Bearer nvapi-...` and never `Bearer Bearer ...`.
   - In `_extract_json`: defensively remove any `<think>.*?</think>` tags before parsing JSON.
   - Maintain backward compatibility of `source` in `SafetyEvaluationResult` (keep `"nvidia_nemotron_guard"` so `tests/test_m1_challenger_stress.py` passes).
   - Ensure comprehensive Vietnamese educational comments (Requirement R4).

2. `src/student_agent/verifier.py`:
   - Implement `VerifierAgent` following the full design in `explorer_m3_2/handoff.md`.
   - Implement `verify_and_assemble(state: CaseInvestigationState, decision: PolicyDecision, trace: TraceWriter | None = None) -> dict[str, Any]`.
   - Implement invariant checks:
     - `no_action` and `needs_investigation`: `recommended_refund_brl == 0.0` and `refund_lines == []`.
     - `action_required`: `recommended_refund_brl == round(sum(lines), 2)` with < 0.001 tolerance and IEEE 754 float rounding.
     - Provenance audit: strictly purge any `evidence_ref` not present in `consumed_evidence_refs` (from MCP Gateway).
     - Secret leak prevention: sanitize any `sk-team-*`, `nvapi-*`, or `Bearer` tokens in output strings.
     - Schema compliance: ensure `data_conflicts` has `minItems: 2` for sources (or omit conflict), cap resolution actions to 8, etc., and validate with `contracts.validate_output`.
     - Trace emission: emit `verification_completed` with `actor="verifier"`, `decision_code="VERIFICATION_PASSED"`, and strictly primitive attributes.
   - Comprehensive Vietnamese educational comments (WHAT, HOW, WHY).

3. `src/student_agent/workflow.py`:
   - Implement `solve_case` and `create_fallback_output` following `explorer_m3_3/handoff.md`.
   - Wire the end-to-end multi-agent pipeline: ToolAdapter -> CoordinatorAgent -> OrderAgent -> PaymentAgent -> ShipmentAgent -> PolicyEngine -> VerifierAgent.
   - Ensure zero-crash error handling via `create_fallback_output` conforming to `day09-l3a-output-v2` with emergency trace emission.
   - Comprehensive Vietnamese educational comments (WHAT, HOW, WHY).

4. Verification:
   - Run compilation and tests:
     - `python -m py_compile src/student_agent/llm_client.py src/student_agent/verifier.py src/student_agent/workflow.py`
     - `pytest -q tests/test_models_invariants.py`
     - `pytest -q tests/test_m1_challenger_stress.py`
     - `pytest -q tests/`
     - If possible, execute test runs or offline case validation and report detailed results.

Deliver your handoff report to `c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\worker_m3_1\handoff.md` and send a message when done.
