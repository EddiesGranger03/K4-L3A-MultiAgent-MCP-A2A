# Task Dispatch: Explorer M2.2 (Policy Engine & Decision Matrix)
- Working directory: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\explorer_m2_2
- Target: Detailed design of `src/student_agent/policy.py`
- Scope Document: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\PROJECT.md
- Original Request: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\ORIGINAL_REQUEST.md

## 2026-09-25T04:43:51Z
Received dispatch as Explorer M2.2:
- Target: Detailed design of `src/student_agent/policy.py`
- Scope: Authoritative evaluation of `EC_POLICY_V1` rules against accumulated facts in `CaseInvestigationState`.
- Explicit decision matrix for all 11 primary issues: `canceled_order_paid`, `unavailable_order_paid`, `late_delivery_seller`, `late_delivery_logistics`, `valid_split_payment`, `payment_mismatch`, `duplicate_charge`, `refund_pending`, `refund_failed`, `unsupported_claim`, `insufficient_evidence`.
- Determine `case_status`: `action_required`, `no_action`, `needs_investigation`.
- Root cause ranking (1..5) with valid `cause_code` matching `^[A-Z][A-Z0-9_]{2,79}$` and `responsible_parties` (`seller`, `platform`, `logistics_provider`, `payment_provider`, `customer`, `unknown`).
- Financial resolution calculations: `currency: "BRL"`, `recommended_refund_brl`, and `refund_lines` (matching status invariants: if `no_action`, refund must be 0 and lines empty; if `action_required`, sum of lines must equal refund amount).
- Resolution actions (max 8 unique strings).
- Comprehensive Vietnamese inline comments (*what*, *how*, *why*) on all classes and methods (R4).
- Strictly READ-ONLY regarding project code.
