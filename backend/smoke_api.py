"""Exercise a running local server: python3 backend/smoke_api.py."""

import argparse
import asyncio
from typing import Any

import httpx


async def smoke(base_url: str) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=60) as client:

        async def check(method: str, path: str, **kwargs: Any) -> httpx.Response:
            response = await client.request(method, path, **kwargs)
            response.raise_for_status()
            print(f"PASS {method:7} {path} ({response.status_code})")
            return response

        health = (await check("GET", "/api/health")).json()
        assert health["mode"] in {"verified_replay", "live_gemini", "live_openai"}
        scenarios = (await check("GET", "/api/scenarios")).json()
        assert len(scenarios["scenarios"]) == 5 and len(scenarios["initial_calendar"]) == 4
        assert len((await check("GET", "/api/prompt-diff")).json()["rules"]) == 4
        comparison = (
            await check(
                "POST",
                "/api/compare-turn1",
                json={"scenario_id": "TC-01", "execution_mode": "replay"},
            )
        ).json()
        assert comparison["v2_result"]["turn1"]["tool_call"] is None
        assert (
            comparison["v1_result"]["turn1"]["tool_call"]["error_reason"]
            == "PREMATURE_UNCONFIRMED_MUTATION"
        )
        body = {
            "conversation_id": comparison["conversation_id"],
            "caller_text": "Yes, please book it.",
        }
        confirmation = (await check("POST", "/api/simulate-turn2", json=body)).json()
        assert confirmation["v2_result"]["db_mutation_result"]["mutated"]
        assert sum(s["status"] == "BOOKED_BY_AGENT" for s in confirmation["calendar"]) == 1
        assert (await client.post("/api/simulate-turn2", json=body)).json() == confirmation
        report = (
            await check("POST", "/api/evaluate-suite", json={"execution_mode": "replay"})
        ).json()
        assert report["v1"]["pass_rate_percent"] == 20
        assert report["v2"]["pass_rate_percent"] == 100
        assert report["v2_confirmation"]["passed"] == 5
        await check("GET", "/docs")
        cors = await check(
            "OPTIONS",
            "/api/compare-turn1",
            headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
        )
        assert cors.headers["access-control-allow-origin"] == "http://localhost:5173"
        print(
            "PASS replay benchmark 20% -> 100%; confirmations 5/5; duplicate booking response unchanged"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    asyncio.run(smoke(parser.parse_args().base_url))
