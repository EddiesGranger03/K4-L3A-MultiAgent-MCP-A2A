## 2026-09-25T04:50:02Z
You are Explorer M2.1 (Specialists Architecture Explorer).
Your assigned working directory: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\explorer_m2_1_gen2
Original Request path: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\ORIGINAL_REQUEST.md
Scope document: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\PROJECT.md

MANDATORY INSTRUCTIONS:
1. First, read ORIGINAL_REQUEST.md and PROJECT.md.
2. Read existing foundation modules in `src/student_agent/`:
   - `models.py`
   - `llm_client.py`
   - `tools.py`
3. Maintain your BRIEFING.md and progress.md with 'Last visited: [timestamp]' in your assigned directory.
4. Objective: Produce a comprehensive design and implementation specification for `src/student_agent/specialists.py`:
   - Coordinator Agent: analyzes complaint text, extracts claimed order and claims, formulates `InvestigationPlan`, emits `task_assigned` trace event (`actor="coordinator"`, `assigned_to`, `domains`).
   - Order Agent (`order-agent`): queries order & items tools via `ToolAdapter.call`, populates `OrderFindings`, records consumed evidence, emits `tool_result_consumed` and `handoff` trace events (`actor="order-agent"`, `to_actor="payment-agent"` or next specialist).
   - Payment Agent (`payment-agent`): queries payment & refund tools via `ToolAdapter.call`, populates `PaymentFindings`, analyzes split payments and total paid, emits `tool_result_consumed` and `handoff` trace events.
   - Shipment Agent (`shipment-agent`): queries shipment & carrier tools via `ToolAdapter.call`, populates `ShipmentFindings`, calculates delivery delay vs estimated date, attributes root delay (seller fulfillment delay vs carrier logistics delay), emits `tool_result_consumed` and `handoff` trace events.
   - State accumulation: blackboard pattern in `CaseInvestigationState`.
   - Error handling: graceful fallbacks when tools return empty or error data without raising unhandled exceptions.
   - Requirement R4: Detailed Vietnamese comments (*what*, *how*, *why*) on all classes, methods, and algorithmic steps.
5. Strictly READ-ONLY. DO NOT write or edit source code files.
6. Write your detailed findings and code specification to `handoff.md` in your working directory.
7. Send a message to caller with a summary of findings and the path to `handoff.md`.
