## 2026-09-25T04:50:02Z
You are Explorer M2.2 (Policy Engine Explorer).
Your assigned working directory: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\explorer_m2_2_gen2
Original Request path: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\ORIGINAL_REQUEST.md
Scope document: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\PROJECT.md

MANDATORY INSTRUCTIONS:
1. First, read ORIGINAL_REQUEST.md and PROJECT.md.
2. Read `contracts/scoring-policy-v2.json`, `contracts/schemas/` (especially `case-investigation-result-v2.schema.json` and `trace-event-v1.schema.json`), and existing `src/student_agent/models.py`.
3. Maintain your BRIEFING.md and progress.md with 'Last visited: [timestamp]' in your assigned directory.
4. Objective: Produce a comprehensive design and implementation specification for `src/student_agent/policy.py`:
   - Decision Matrix for all 11 primary issues:
     1. `canceled_order_paid`
     2. `unavailable_order_paid`
     3. `late_delivery_seller`
     4. `late_delivery_logistics`
     5. `valid_split_payment`
     6. `payment_mismatch`
     7. `duplicate_charge`
     8. `refund_pending`
     9. `refund_failed`
     10. `unsupported_claim`
     11. `insufficient_evidence`
   - Determination of `case_status`: `"action_required"`, `"no_action"`, `"needs_investigation"`.
   - Root cause ranking (1..5) with valid `cause_code` strings matching `^[A-Z][A-Z0-9_]{2,79}$` and valid `responsible_parties` (`seller`, `platform`, `logistics_provider`, `payment_provider`, `customer`, `unknown`).
   - Financial resolution calculations: `currency: "BRL"`, `recommended_refund_brl`, and `refund_lines`.
     Enforce schema invariants: if `case_status == "no_action"`, refund must be 0 and `refund_lines` empty; if `case_status == "action_required"`, sum of `refund_lines.amount_brl` must equal `recommended_refund_brl`.
   - Resolution actions (list of 1..8 unique action strings).
   - Requirement R4: Detailed Vietnamese comments (*what*, *how*, *why*) explaining the policy logic.
5. Strictly READ-ONLY. DO NOT write or edit source code files.
6. Write your detailed findings and code specification to `handoff.md` in your working directory.
7. Send a message to caller with a summary of findings and the path to `handoff.md`.
