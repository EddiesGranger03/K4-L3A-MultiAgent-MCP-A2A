## 2026-09-25T04:59:31Z
You are Worker M2.1 (Specialists & Policy Engine Implementer).
Your assigned working directory: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\worker_m2_1_gen2
Original Request path: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\ORIGINAL_REQUEST.md
Scope document: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\PROJECT.md

Explorer Reports:
- M2.1 (Specialists Architecture): c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\explorer_m2_1_gen2\handoff.md
- M2.2 (Policy Engine & Decision Matrix): c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\explorer_m2_2_gen2\handoff.md
- M2.3 (Evidence Mapping & Trace Integration): c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\explorer_m2_3_gen2\handoff.md

WRITE OWNERSHIP (STRICT BOUNDARIES):
You own exclusively:
- `src/student_agent/specialists.py`
- `src/student_agent/policy.py`
You MUST NOT modify any other source files or test files.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

MANDATORY INSTRUCTIONS:
1. First, read ORIGINAL_REQUEST.md, PROJECT.md, and the three Explorer reports listed above.
2. Maintain BRIEFING.md and progress.md with 'Last visited: [timestamp]' in your assigned directory.
3. Implement `src/student_agent/specialists.py`:
   - `CoordinatorAgent`: parses `CaseInput`, runs safety & intent checks, builds `InvestigationPlan`, initializes `CaseInvestigationState`, emits `task_assigned` trace event (`actor="coordinator"`).
   - `OrderAgent`: calls `order` and `item` tools via `ToolAdapter.call`, populates `OrderFindings`, extracts items & seller_ids, computes `total_order_value`, records evidence, emits `handoff` trace event (`actor="order-agent"`, `target="payment-agent"`).
   - `PaymentAgent`: calls `payment` and `refund` tools via `ToolAdapter.call`, populates `PaymentFindings`, analyzes split payments, mismatches, and duplicate charges, records evidence, emits `handoff` trace event (`actor="payment-agent"`, `target="shipment-agent"`).
   - `ShipmentAgent`: calls `shipment` tools via `ToolAdapter.call`, populates `ShipmentFindings`, calculates delivery delays, attributes seller vs logistics delays, records evidence, emits `handoff` trace event (`actor="shipment-agent"`, `target="policy-agent"`).
   - `run_specialists_pipeline(state, llm_client, tool_adapter, trace)` helper to run the blackboard sequence.
   - Robust error handling: all tool calls wrapped in try/except, logging errors to `state.errors`, never crashing.
4. Implement `src/student_agent/policy.py`:
   - Decision Matrix for all 11 primary issues: `canceled_order_paid`, `unavailable_order_paid`, `late_delivery_seller`, `late_delivery_logistics`, `valid_split_payment`, `payment_mismatch`, `duplicate_charge`, `refund_pending`, `refund_failed`, `unsupported_claim`, `insufficient_evidence`.
   - `PolicyEngine`: method `evaluate(state: CaseInvestigationState) -> PolicyDecision`.
   - Invariant enforcement:
     * If `case_status == "no_action"`, `recommended_refund_brl == 0.0` and `refund_lines == []`.
     * If `case_status == "action_required"`, `recommended_refund_brl == sum(lines.amount_brl)`.
     * If `case_status == "needs_investigation"`, `recommended_refund_brl == 0.0` and `refund_lines == []`.
   - Cause codes matching `^[A-Z][A-Z0-9_]{2,79}$` and `responsible_parties` from schema enum.
   - Claim Assessment Adjudication: evaluate each customer claim, link only genuine `evidence_refs` consumed by `ToolAdapter`.
   - Cross-domain conflict detection with `sources` minItems: 2.
   - Emits `policy_decided` trace event (`actor="policy-agent"`, `target="verifier"`).
5. Requirement R4: Complete, detailed inline Vietnamese comments (*what*, *how*, *why*) on all classes, methods, and algorithmic blocks for educational clarity.
6. Verification: Run Python syntax compilation (`python -m py_compile ...`), import verification, and existing tests (`pytest -q` or targeted pytest). Document commands and exact outputs in your handoff report.
7. Write `handoff.md` in your working directory and notify the parent via `send_message`.
