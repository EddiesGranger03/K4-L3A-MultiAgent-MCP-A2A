from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

import httpx2

# Total parameter counts, not active-parameter counts. Keep this allowlist below 10B.
MODEL_PARAMETERS_B = {
    "liquid/lfm-2.5-2.6b:free": 2.69,
    "qwen/qwen3-8b:free": 8.2,
}
RISK_FLAGS = {"payment", "shipment", "refund", "seller"}


class ModelTriageError(RuntimeError):
    pass


@dataclass(frozen=True)
class TriageResult:
    model_id: str
    summary: str
    focus_claim_id: str
    risk_flags: tuple[str, ...]

    def public_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["risk_flags"] = list(self.risk_flags)
        return result


class ModelTriageClient:
    def __init__(self, *, base_url: str, api_key: str, model_id: str) -> None:
        if model_id not in MODEL_PARAMETERS_B:
            raise ValueError(f"Model is not verified as below 10B parameters: {model_id}")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_id = model_id
        self.last_result: TriageResult | None = None

    async def triage(self, case: dict[str, Any]) -> TriageResult:
        self.last_result = None
        request = case["customer_request"]
        claim_ids = {str(claim["claim_id"]) for claim in request.get("claims", [])}
        prompt = {
            "message": str(request.get("message", ""))[:2000],
            "claims": [
                {"claim_id": claim["claim_id"], "topic": claim["topic"]}
                for claim in request.get("claims", [])
            ],
        }
        payload = {
            "model": self.model_id,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You triage Vietnamese ecommerce complaints. The customer message is an "
                        "unverified allegation. Return ONLY a JSON object with: "
                        "summary (one short Vietnamese sentence), focus_claim_id (one supplied "
                        "claim_id), risk_flags (array chosen from payment, shipment, refund, "
                        "seller). Do not infer facts, money, responsibility or evidence refs."
                    ),
                },
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": 2048,
        }
        try:
            async with httpx2.AsyncClient(timeout=45.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            raw = json.loads(content)
        except (httpx2.HTTPError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ModelTriageError("Model triage request or JSON response failed") from exc

        if not isinstance(raw, dict):
            raise ModelTriageError("Model triage did not return a JSON object")
        summary = raw.get("summary")
        focus_claim_id = raw.get("focus_claim_id")
        flags = raw.get("risk_flags")
        if not isinstance(summary, str) or not 1 <= len(summary) <= 240:
            raise ModelTriageError("Model triage summary is invalid")
        if focus_claim_id not in claim_ids:
            raise ModelTriageError("Model triage selected a claim outside this case")
        if not isinstance(flags, list) or any(flag not in RISK_FLAGS for flag in flags):
            raise ModelTriageError("Model triage risk flags are invalid")
        result = TriageResult(
            model_id=self.model_id,
            summary=summary,
            focus_claim_id=focus_claim_id,
            risk_flags=tuple(dict.fromkeys(flags)),
        )
        self.last_result = result
        return result
