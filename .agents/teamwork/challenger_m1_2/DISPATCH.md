# Task Dispatch: Challenger M1.2 (ToolAdapter Anti-Hallucination & Fallback Stress Test)
- Working directory: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\challenger_m1_2
- Scope Document: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\PROJECT.md
- Original Request: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\ORIGINAL_REQUEST.md
- Target: Stress test `src/student_agent/tools.py` and `src/student_agent/llm_client.py`

## 2026-09-25T04:33:40Z
You are Challenger M1.2 (ToolAdapter & LLM Fallback Stress Verifier).
Your assigned working directory: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\challenger_m1_2
Scope document: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\PROJECT.md
Original Request path: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\ORIGINAL_REQUEST.md
Worker handoff report: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\worker_m1_1\handoff.md

CRITICAL INSTRUCTIONS:
1. First, read ORIGINAL_REQUEST.md and PROJECT.md.
2. Read your DISPATCH.md and worker_m1_1/handoff.md.
3. Maintain your progress.md with 'Last visited: [timestamp]'.
4. Adversarially stress test `src/student_agent/tools.py` and `src/student_agent/llm_client.py`:
   - ToolAdapter: Anti-hallucination check (attempt to inject fake ref into `filter_valid_refs` and ensure it is discarded; verify `consumed_evidence_refs` cannot be poisoned).
   - ToolAdapter: Trace emission check (verify `tool_result_consumed` event structure and schema validity against `contracts/schemas/trace-event-v1.schema.json`).
   - LLM Client: Fallback engine check (simulate offline mode / mock failed HTTP responses for `evaluate_safety`, `analyze_intent`, `assist_claim_verification`, and verify deterministic return without crashing).
   - Write and run empirical test scripts to verify these capabilities.
5. Record your findings in handoff.md with an explicit verdict: **APPROVE** or **REJECT**.
6. Send a message to caller (parent) with your verdict and summary.
