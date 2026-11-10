"""Runtime response bodies and OpenAPI describe the same public contract."""

import unittest
from unittest.mock import AsyncMock, patch

import httpx
from pydantic import ValidationError

from backend.agent_runner import AgentRunner
from backend.config import HarnessError, Settings
from backend.main import create_app
from backend.models import ErrorResponse, HealthResponse, PromptDiffResponse, ScenariosResponse


class ContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.settings = Settings(execution_mode="replay")
        self.runner = AgentRunner(self.settings)
        self.app = create_app(self.settings, self.runner)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test"
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    async def test_get_responses_have_strict_runtime_and_openapi_schemas(self) -> None:
        schema = self.app.openapi()
        for path, model in (
            ("/api/health", HealthResponse),
            ("/api/scenarios", ScenariosResponse),
            ("/api/prompt-diff", PromptDiffResponse),
        ):
            with self.subTest(path=path):
                response = await self.client.get(path)
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(model.model_validate(body).model_dump(mode="json"), body)
                documented = schema["paths"][path]["get"]["responses"]["200"]
                self.assertEqual(
                    documented["content"]["application/json"]["schema"],
                    {"$ref": f"#/components/schemas/{model.__name__}"},
                )
                self.assertIs(
                    schema["components"]["schemas"][model.__name__]["additionalProperties"], False
                )
                with self.assertRaises(ValidationError):
                    model.model_validate({**body, "unexpected": True})

    async def test_validation_error_schema_matches_actual_envelope(self) -> None:
        schema = self.app.openapi()
        for path in ("/api/compare-turn1", "/api/simulate-turn2", "/api/evaluate-suite"):
            with self.subTest(path=path):
                response = await self.client.post(path, json={"unexpected": True})
                self.assertEqual(response.status_code, 422)
                body = response.json()
                parsed = ErrorResponse.model_validate(body)
                self.assertEqual(parsed.error.code, "INVALID_REQUEST")
                self.assertTrue(parsed.error.details)
                self.assertNotIn("detail", body)
                documented = schema["paths"][path]["post"]["responses"]["422"]
                self.assertEqual(
                    documented["content"]["application/json"]["schema"],
                    {"$ref": "#/components/schemas/ErrorResponse"},
                )
        self.assertNotIn("HTTPValidationError", schema["components"]["schemas"])

    async def test_domain_errors_preserve_existing_fields_and_documented_status(self) -> None:
        for path, body, status, code in (
            ("/api/compare-turn1", {"caller_text": "Hello"}, 409, "LIVE_MODE_REQUIRED"),
            (
                "/api/simulate-turn2",
                {"conversation_id": "unknown", "caller_text": "Yes"},
                404,
                "CONVERSATION_NOT_FOUND",
            ),
            ("/api/evaluate-suite", {"execution_mode": "live"}, 503, "API_KEY_REQUIRED"),
        ):
            with self.subTest(path=path, code=code):
                response = await self.client.post(path, json=body)
                self.assertEqual(response.status_code, status)
                parsed = ErrorResponse.model_validate(response.json())
                self.assertEqual(parsed.error.code, code)
                self.assertEqual(set(response.json()["error"]), {"code", "message"})
                self.assertIn(str(status), self.app.openapi()["paths"][path]["post"]["responses"])

    async def test_provider_error_envelopes_do_not_expose_internal_details(self) -> None:
        for status, code in ((502, "INVALID_MODEL_RESPONSE"), (504, "PROVIDER_TIMEOUT")):
            with self.subTest(status=status):
                with patch.object(
                    self.runner,
                    "compare",
                    AsyncMock(side_effect=HarnessError(code, "Provider request failed.", status)),
                ):
                    response = await self.client.post(
                        "/api/compare-turn1", json={"scenario_id": "TC-01"}
                    )
                self.assertEqual(response.status_code, status)
                self.assertEqual(ErrorResponse.model_validate(response.json()).error.code, code)
                documented = self.app.openapi()["paths"]["/api/compare-turn1"]["post"]["responses"][
                    str(status)
                ]
                self.assertEqual(
                    documented["content"]["application/json"]["schema"],
                    {"$ref": "#/components/schemas/ErrorResponse"},
                )


if __name__ == "__main__":
    unittest.main()
