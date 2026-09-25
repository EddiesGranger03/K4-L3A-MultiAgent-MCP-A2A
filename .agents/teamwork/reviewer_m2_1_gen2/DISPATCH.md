## 2026-09-25T05:08:12Z
You are Reviewer M2.1 (Contract & Policy Reviewer).
Your assigned working directory: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\reviewer_m2_1_gen2
Original Request path: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\ORIGINAL_REQUEST.md
Scope document: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\PROJECT.md
Worker Handoff path: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\worker_m2_1_rep\handoff.md

Target files to review:
- `src/student_agent/specialists.py`
- `src/student_agent/policy.py`

MANDATORY INSTRUCTIONS:
1. First, read ORIGINAL_REQUEST.md and PROJECT.md.
2. Read the worker handoff report at the path above.
3. Maintain BRIEFING.md and progress.md with 'Last visited: [timestamp]' in your assigned directory.
4. Review `src/student_agent/policy.py` and `src/student_agent/specialists.py`:
   - Verify coverage of all 11 primary issues in `PolicyEngine` against `contracts/scoring-policy-v2.json`.
   - Verify schema invariants: if `case_status == "no_action"` or `"needs_investigation"`, `recommended_refund_brl == 0.0` and `refund_lines == []`. If `case_status == "action_required"`, `recommended_refund_brl == sum(lines.amount_brl)`.
   - Verify regex for `cause_code` (`^[A-Z][A-Z0-9_]{2,79}$`) and valid `responsible_parties` enum values.
   - Verify `DataConflict` has `sources` with `minItems: 2` and unique items.
   - Verify Claim Assessment Adjudication only attaches genuine `evidence_refs` consumed by `ToolAdapter`.
   - Verify Requirement R4: Comprehensive Vietnamese comments (*what*, *how*, *why*) on all classes and functions.
   - Run compilation and tests: `python -m py_compile src/student_agent/specialists.py src/student_agent/policy.py`, `pytest -q tests/test_models_invariants.py`.
5. Deliver verdict: APPROVE or REQUEST_CHANGES.
6. Write full review and verdict to `handoff.md` and send message to caller.
