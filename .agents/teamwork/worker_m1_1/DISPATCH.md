# Task Dispatch: Worker M1.1 (Foundation Implementation)
- Working directory: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\worker_m1_1
- Target: Implement `src/student_agent/models.py`, `src/student_agent/llm_client.py`, and `src/student_agent/tools.py`
- Scope Document: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\PROJECT.md
- Original Request: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\ORIGINAL_REQUEST.md

## 2026-09-25T04:24:41Z
You are Worker M1.1 (Foundation Implementer).
Your assigned working directory: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\worker_m1_1
Scope document: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\PROJECT.md
Original Request path: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\ORIGINAL_REQUEST.md

CRITICAL INSTRUCTIONS:
1. First, read ORIGINAL_REQUEST.md and PROJECT.md at the paths above.
2. Read your DISPATCH.md in your working directory.
3. Maintain your progress.md in your working directory with 'Last visited: [timestamp]'. Update it as you make progress.
4. Read the thorough designs and code prepared by the 3 Explorers:
   - Explorer M1.1 (Models): c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\explorer_m1_1\handoff.md and proposed_models.py
   - Explorer M1.2 (LLM Client): c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\explorer_m1_2\handoff.md and proposed_llm_client.py
   - Explorer M1.3 (Tool Adapter): c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\explorer_m1_3\handoff.md

WRITE OWNERSHIP:
You have exclusive write ownership of these 3 files:
- `src/student_agent/models.py`
- `src/student_agent/llm_client.py`
- `src/student_agent/tools.py`
Do NOT modify any other files outside your assigned write ownership.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

REQUIREMENTS:
- Implement `src/student_agent/models.py` based on Explorer M1.1's design.
- Implement `src/student_agent/llm_client.py` based on Explorer M1.2's design (using NVIDIA API key `Bearer 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`, model `nvidia/llama-3.1-nemotron-safety-guard-8b-v3`, `httpx2.AsyncClient`, with robust fallback mechanisms).
- Implement `src/student_agent/tools.py` based on Explorer M1.3's design (ToolAdapter, dynamic discovery, safe call, anti-hallucination tracking, automatic `tool_result_consumed` trace emission).
- Every major class, method, and logical step MUST include comprehensive educational comments in Vietnamese (*what*, *how*, *why*) per Requirement R4.
- Verification: run compile checks (`python -m py_compile src/student_agent/models.py src/student_agent/llm_client.py src/student_agent/tools.py`), run linter (`ruff check src/student_agent/models.py src/student_agent/llm_client.py src/student_agent/tools.py`), and run `pytest -q` to ensure no regression.
- Document verification commands and output in your `handoff.md`.
- Send a message to caller (parent) when complete referencing your `handoff.md`.
