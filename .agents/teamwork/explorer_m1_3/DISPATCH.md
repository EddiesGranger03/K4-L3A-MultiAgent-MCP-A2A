# Task Dispatch: Explorer M1.3 (Tool Adapter & Evidence Tracker)
- Working directory: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\explorer_m1_3
- Target: Detailed design of `src/student_agent/tools.py`
- Scope Document: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\PROJECT.md
- Original Request: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\ORIGINAL_REQUEST.md

## 2026-09-25T04:12:43Z
You are Explorer M1.3 (Tool Adapter & Evidence Tracker Explorer).
Your assigned working directory: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\explorer_m1_3
Scope document: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\PROJECT.md
Original Request path: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\ORIGINAL_REQUEST.md

CRITICAL INSTRUCTIONS:
1. First, read ORIGINAL_REQUEST.md and PROJECT.md at the paths above.
2. Read your DISPATCH.md in your working directory.
3. Maintain your progress.md in your working directory with 'Last visited: [timestamp]'. Update it as you make progress.
4. Objective: Produce the exact architecture, class design, and implementation specification for `src/student_agent/tools.py`.
   - ToolAdapter wrapping `EvidenceGateway` and `TraceWriter`.
   - Dynamic discovery of tools via `await gateway.list_tools()`.
   - Safe call wrapper: passes `case_id`, validates envelope, unpacks data, tracks all returned `evidence_ref` in `self.consumed_evidence_refs: set[str]`.
   - Emits `tool_result_consumed` trace event immediately upon each successful tool call with exact `evidence_refs=[envelope["evidence_ref"]]` and `tool_name`.
   - Enforces strict anti-hallucination: only genuine `evidence_ref` items returned by the gateway are stored or tracked.
   - Design detailed Vietnamese inline comments (*what*, *how*, *why*) for all methods and classes (R4).
5. You are strictly READ-ONLY. DO NOT write or modify any source code files. Write only to your assigned directory (.agents/teamwork/explorer_m1_3).
6. Document your findings and complete code specification in handoff.md in your working directory.
7. Send a message to caller (parent) with a summary and the path to your handoff.md when complete.
