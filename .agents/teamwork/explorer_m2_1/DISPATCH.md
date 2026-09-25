# Task Dispatch: Explorer M2.1 (Specialist Agents Architecture)
- Working directory: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\explorer_m2_1
- Target: Detailed design of `src/student_agent/specialists.py`
- Scope Document: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\PROJECT.md
- Original Request: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\ORIGINAL_REQUEST.md

## 2026-09-25T04:43:51Z
You are Explorer M2.1 (Specialist Agents Architecture Explorer).
Your assigned working directory: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\explorer_m2_1
Scope document: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\PROJECT.md
Original Request path: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\ORIGINAL_REQUEST.md

CRITICAL INSTRUCTIONS:
1. First, read ORIGINAL_REQUEST.md and PROJECT.md.
2. Read your DISPATCH.md and view existing foundation modules:
   - `src/student_agent/models.py`
   - `src/student_agent/llm_client.py`
   - `src/student_agent/tools.py`
3. Maintain your progress.md with 'Last visited: [timestamp]'.
4. Objective: Design `src/student_agent/specialists.py` in detail:
   - Coordinator Agent: extracts `claimed_order_id`, analyzes customer message, formulates `InvestigationPlan`, emits `task_assigned` trace event.
   - Order Agent (`order-agent`): queries order & item tools via `ToolAdapter.call`, stores `OrderFindings`, emits `tool_result_consumed` and `handoff` trace events.
   - Payment Agent (`payment-agent`): queries payment & refund tools via `ToolAdapter.call`, stores `PaymentFindings`, evaluates split payments and total paid, emits `tool_result_consumed` and `handoff` trace events.
   - Shipment Agent (`shipment-agent`): queries shipment tools, analyzes carrier tracking vs estimated delivery date, attributes delays (seller late vs carrier logistics delay), stores `ShipmentFindings`, emits `tool_result_consumed` and `handoff` trace events.
   - Blackboard state accumulation in `CaseInvestigationState`.
   - Comprehensive Vietnamese inline comments (*what*, *how*, *why*) on all classes and methods (R4).
5. You are strictly READ-ONLY. DO NOT write or modify source code. Write only to your assigned directory.
6. Record your findings and complete code specification in handoff.md.
7. Send a message to caller (parent) with summary and path to handoff.md when complete.
