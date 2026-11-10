import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from google import genai
from openai import AsyncOpenAI

from backend.agent_runner import ProviderGateway
from backend.config import HarnessError, Settings
from backend.models import AgentDecision
from backend.scenarios import SCENARIOS


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    def gateway(self, provider, *, timeout_seconds=0.05):
        return ProviderGateway(
            Settings(
                provider=provider,
                execution_mode="live",
                openai_api_key="test-only",
                gemini_api_key="test-only",
                timeout_seconds=timeout_seconds,
            )
        )

    async def test_openai_structured_response_and_resource_cleanup(self):
        gateway = self.gateway("openai")
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(refusal=None, parsed=SCENARIOS[0].v2))]
        )
        parse = AsyncMock(return_value=response)
        client = MagicMock()
        client.chat.completions.parse = parse
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=client)
        manager.__aexit__ = AsyncMock(return_value=False)
        with patch("backend.agent_runner.AsyncOpenAI", return_value=manager) as factory:
            result = await gateway.generate("System facts", {"caller_text": "Hello"})
        self.assertEqual(result, SCENARIOS[0].v2)
        self.assertEqual(parse.call_args.kwargs["response_format"], AgentDecision)
        self.assertEqual(parse.call_args.kwargs["model"], "gpt-4o-mini")
        self.assertEqual(factory.call_args.kwargs["max_retries"], 0)
        manager.__aexit__.assert_awaited_once()

    async def test_openai_refusal_and_malformed_response(self):
        for message, expected in [
            (SimpleNamespace(refusal="Cannot comply", parsed=None), "PROVIDER_REFUSAL"),
            (
                SimpleNamespace(refusal=None, parsed={"agent_reply": "Hello"}),
                "INVALID_MODEL_RESPONSE",
            ),
            (SimpleNamespace(refusal=None, parsed=None), "INVALID_MODEL_RESPONSE"),
        ]:
            with self.subTest(expected=expected):
                gateway = self.gateway("openai")
                client = MagicMock()
                client.chat.completions.parse = AsyncMock(
                    return_value=SimpleNamespace(choices=[SimpleNamespace(message=message)])
                )
                manager = MagicMock()
                manager.__aenter__ = AsyncMock(return_value=client)
                manager.__aexit__ = AsyncMock(return_value=False)
                with patch("backend.agent_runner.AsyncOpenAI", return_value=manager):
                    with self.assertRaises(HarnessError) as context:
                        await gateway.generate("System facts", {})
                self.assertEqual(context.exception.code, expected)
                self.assertEqual(client.chat.completions.parse.await_count, 1)

    async def test_gemini_structured_response_and_cleanup(self):
        gateway = self.gateway("gemini")
        generate = AsyncMock(
            return_value=SimpleNamespace(
                text=SCENARIOS[0].v2.model_dump_json(), prompt_feedback=None, candidates=[]
            )
        )
        client = MagicMock()
        client.aio.models.generate_content = generate
        client.aio.aclose = AsyncMock()
        with patch("backend.agent_runner.genai.Client", return_value=client) as factory:
            result = await gateway.generate("System facts", {"caller_text": "Hello"})
        self.assertEqual(result, SCENARIOS[0].v2)
        self.assertEqual(generate.call_args.kwargs["model"], "gemini-2.5-flash")
        self.assertEqual(generate.call_args.kwargs["config"].response_schema, AgentDecision)
        self.assertEqual(factory.call_args.kwargs["http_options"].retry_options.attempts, 1)
        client.aio.aclose.assert_awaited_once()
        client.close.assert_called_once()

    async def test_gemini_malformed_and_refusal(self):
        for text, feedback, code in [
            ("not JSON", None, "INVALID_MODEL_RESPONSE"),
            ('{"agent_reply": "Hello"}', None, "INVALID_MODEL_RESPONSE"),
            (None, SimpleNamespace(block_reason="SAFETY"), "PROVIDER_REFUSAL"),
        ]:
            gateway = self.gateway("gemini")
            client = MagicMock()
            client.aio.models.generate_content = AsyncMock(
                return_value=SimpleNamespace(text=text, prompt_feedback=feedback, candidates=[])
            )
            client.aio.aclose = AsyncMock()
            with patch("backend.agent_runner.genai.Client", return_value=client):
                with self.assertRaises(HarnessError) as context:
                    await gateway.generate("System facts", {})
            self.assertEqual(context.exception.code, code)
            client.aio.aclose.assert_awaited_once()

    async def test_transient_errors_bounded_retries_for_both_providers(self):
        for provider in ("openai", "gemini"):
            for error in (
                TimeoutError(),
                httpx.ConnectError("No connection"),
                SimpleProviderError(503),
                SimpleProviderError(429),
            ):
                with self.subTest(provider=provider, error=type(error).__name__):
                    gateway = self.gateway(provider)
                    operation = AsyncMock(side_effect=[error, SCENARIOS[0].v2])
                    setattr(gateway, "_" + provider, operation)
                    self.assertEqual(await gateway.generate("System facts", {}), SCENARIOS[0].v2)
                    self.assertEqual(operation.await_count, 2)

    async def test_timeout_exhaustion_authentication_and_unavailable_model(self):
        for provider in ("openai", "gemini"):
            for error, code, calls in [
                (TimeoutError(), "PROVIDER_TIMEOUT", 2),
                (SimpleProviderError(401), "PROVIDER_AUTHENTICATION_FAILED", 1),
                (SimpleProviderError(403), "PROVIDER_AUTHENTICATION_FAILED", 1),
                (SimpleProviderError(404), "PROVIDER_MODEL_UNAVAILABLE", 1),
                (SimpleProviderError(503), "PROVIDER_UNAVAILABLE", 2),
            ]:
                with self.subTest(provider=provider, code=code):
                    gateway = self.gateway(provider)
                    operation = AsyncMock(side_effect=error)
                    setattr(gateway, "_" + provider, operation)
                    with self.assertRaises(HarnessError) as context:
                        await gateway.generate("System facts", {})
                    self.assertEqual(context.exception.code, code)
                    self.assertEqual(operation.await_count, calls)
                    self.assertNotIn("test-only", context.exception.message)

    async def test_outer_timeout_bounds_a_stalled_client(self):
        async def stalled(*args):
            import asyncio

            await asyncio.sleep(2)

        for provider in ("openai", "gemini"):
            gateway = self.gateway(provider)
            setattr(gateway, "_" + provider, stalled)
            with self.assertRaises(HarnessError) as context:
                await gateway.generate("System facts", {})
            self.assertEqual(context.exception.code, "PROVIDER_TIMEOUT")

    async def test_openai_real_sdk_transport_parses_and_validates(self):
        """Exercise SDK JSON schema serialization and parsing, without a network."""
        cases = (
            ({"content": SCENARIOS[0].v2.model_dump_json()}, None),
            ({"content": '{"agent_reply": "Hello"}'}, "INVALID_MODEL_RESPONSE"),
            ({"content": "not JSON"}, "INVALID_MODEL_RESPONSE"),
            ({"content": None, "refusal": "Cannot comply"}, "PROVIDER_REFUSAL"),
        )
        for message, expected_error in cases:
            with self.subTest(expected_error=expected_error, message=message):
                requests = []

                def respond(request):
                    requests.append(json.loads(request.content))
                    return httpx.Response(
                        200,
                        json={
                            "id": "chatcmpl-offline-test",
                            "object": "chat.completion",
                            "created": 0,
                            "model": "gpt-4o-mini",
                            "choices": [
                                {
                                    "index": 0,
                                    "finish_reason": "stop",
                                    "message": {"role": "assistant", **message},
                                }
                            ],
                        },
                    )

                async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:

                    def factory(**kwargs):
                        return AsyncOpenAI(**kwargs, http_client=http_client)

                    gateway = self.gateway("openai", timeout_seconds=2)
                    with patch("backend.agent_runner.AsyncOpenAI", side_effect=factory):
                        if expected_error:
                            with self.assertRaises(HarnessError) as context:
                                await gateway.generate("System facts", {"caller_text": "Hello"})
                            self.assertEqual(context.exception.code, expected_error)
                        else:
                            self.assertEqual(
                                await gateway.generate("System facts", {}), SCENARIOS[0].v2
                            )
                self.assertEqual(len(requests), 1)
                schema = requests[0]["response_format"]
                self.assertEqual(schema["type"], "json_schema")
                self.assertTrue(schema["json_schema"]["strict"])
                self.assertFalse(schema["json_schema"]["schema"]["additionalProperties"])

    async def test_gemini_real_sdk_transport_parses_and_validates(self):
        """Exercise actual GenAI request conversion and response validation offline."""
        cases = (
            (
                {
                    "candidates": [
                        {
                            "content": {
                                "role": "model",
                                "parts": [{"text": SCENARIOS[0].v2.model_dump_json()}],
                            },
                            "finishReason": "STOP",
                        }
                    ]
                },
                None,
            ),
            (
                {
                    "candidates": [
                        {
                            "content": {
                                "role": "model",
                                "parts": [{"text": '{"agent_reply": "Hello"}'}],
                            },
                            "finishReason": "STOP",
                        }
                    ]
                },
                "INVALID_MODEL_RESPONSE",
            ),
            (
                {
                    "candidates": [
                        {
                            "content": {"role": "model", "parts": [{"text": "not JSON"}]},
                            "finishReason": "STOP",
                        }
                    ]
                },
                "INVALID_MODEL_RESPONSE",
            ),
            ({"promptFeedback": {"blockReason": "SAFETY"}}, "PROVIDER_REFUSAL"),
            ({"candidates": [{"finishReason": "SAFETY"}]}, "PROVIDER_REFUSAL"),
        )
        real_client = genai.Client
        for response, expected_error in cases:
            with self.subTest(expected_error=expected_error, response=response):
                requests = []

                def respond(request):
                    requests.append(json.loads(request.content))
                    return httpx.Response(200, json=response)

                async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:

                    def factory(**kwargs):
                        options = kwargs["http_options"].model_copy(
                            update={"httpx_async_client": http_client}
                        )
                        return real_client(**{**kwargs, "http_options": options})

                    gateway = self.gateway("gemini", timeout_seconds=2)
                    with patch("backend.agent_runner.genai.Client", side_effect=factory):
                        if expected_error:
                            with self.assertRaises(HarnessError) as context:
                                await gateway.generate("System facts", {"caller_text": "Hello"})
                            self.assertEqual(context.exception.code, expected_error)
                        else:
                            self.assertEqual(
                                await gateway.generate("System facts", {}), SCENARIOS[0].v2
                            )
                self.assertEqual(len(requests), 1)
                config = requests[0]["generationConfig"]
                self.assertEqual(config["responseMimeType"], "application/json")
                self.assertIn("agent_reply", config["responseSchema"]["properties"])


class SimpleProviderError(Exception):
    def __init__(self, status):
        self.status_code = status
        self.code = status
        super().__init__("Sensitive provider detail must not reach the API.")


if __name__ == "__main__":
    unittest.main()
