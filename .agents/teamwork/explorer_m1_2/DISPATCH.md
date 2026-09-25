# Task Dispatch: Explorer M1.2 (NVIDIA LLM Client Integration)
- Working directory: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\explorer_m1_2
- Target: Detailed design of `src/student_agent/llm_client.py`
- Scope Document: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\PROJECT.md
- Original Request: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\ORIGINAL_REQUEST.md

## 2026-09-25T04:12:43Z
You are Explorer M1.2 (NVIDIA LLM Client Explorer).
Your assigned working directory: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\explorer_m1_2
Scope document: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\PROJECT.md
Original Request path: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\ORIGINAL_REQUEST.md

CRITICAL INSTRUCTIONS:
1. First, read ORIGINAL_REQUEST.md and PROJECT.md at the paths above.
2. Read your DISPATCH.md in your working directory.
3. Maintain your progress.md in your working directory with 'Last visited: [timestamp]'. Update it as you make progress.
4. Objective: Produce the exact architecture, class design, and implementation specification for `src/student_agent/llm_client.py`.
   - Must use the provided NVIDIA API key: `Bearer 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`
   - Must use model: `nvidia/llama-3.1-nemotron-safety-guard-8b-v3`
   - Must use `httpx2.AsyncClient` targeting `https://integrate.api.nvidia.com/v1/chat/completions` (no external SDKs).
   - Design methods for: intent analysis, safety risk assessment, and claim verification assistance.
   - Include robust fallback handling (timeout, rate limit, network failure) so that the multi-agent pipeline never crashes even if the remote API is unreachable.
   - Design detailed Vietnamese inline comments (*what*, *how*, *why*) on all classes and functions (R4).
5. You are strictly READ-ONLY. DO NOT write or modify any source code files. Write only to your assigned directory (.agents/teamwork/explorer_m1_2).
6. Document your findings and complete code specification in handoff.md in your working directory.
7. Send a message to caller (parent) with a summary and the path to your handoff.md when complete.
