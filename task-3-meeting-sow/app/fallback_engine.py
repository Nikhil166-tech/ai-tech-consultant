import os
import time
import json
import random
import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple, Callable
import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger("Task3ModelFallbackEngine")

STABLE_GEMINI_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
]

PREVIEW_GEMINI_MODELS = [
    "gemini-3-flash-preview",
    "gemini-3.1-pro-preview",
]

STABLE_CLAUDE_MODELS = [
    "claude-haiku-5-5",
    "claude-sonnet-5-5",
    "claude-opus-5-5",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
]

DEPRECATED_MODELS = {
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "claude-3-7-sonnet-latest",
    "claude-3-5-sonnet-latest",
    "claude-3-5-haiku-latest",
    "claude-3-haiku-20240307",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
}

ROLE_ENV_VARS = {
    "KNOWLEDGE_ANSWER": ("MODEL_KNOWLEDGE_ANSWER", "MODEL_KNOWLEDGE_ANSWER_FALLBACKS"),
    "KB_ANSWER": ("MODEL_KB_ANSWER", "MODEL_KB_ANSWER_FALLBACKS"),
    "EMAIL_CLASSIFICATION": ("MODEL_CLASSIFICATION", "MODEL_CLASSIFICATION_FALLBACKS"),
    "EMAIL_DRAFTING": ("MODEL_DRAFTING", "MODEL_DRAFTING_FALLBACKS"),
    "REQUIREMENTS_EXTRACTION": ("MODEL_REQUIREMENTS_EXTRACTION", "MODEL_REQUIREMENTS_EXTRACTION_FALLBACKS"),
    "CAPABILITY_CHECKING": ("MODEL_CAPABILITY_CHECKING", "MODEL_CAPABILITY_CHECKING_FALLBACKS"),
}

ESTIMATED_COST_PER_1K_TOKENS = {
    "gemini-3.5-flash": 0.0001,
    "gemini-3.5-flash-lite": 0.00005,
    "gemini-3.1-flash-lite": 0.00005,
    "gemini-flash-latest": 0.0001,
    "gemini-3-flash-preview": 0.0001,
    "claude-haiku-5-5": 0.0008,
    "claude-sonnet-5-5": 0.003,
}


class ModelAttemptRecord(BaseModel):
    model: str
    provider: str
    status: str
    http_status: Optional[int] = None
    latency_ms: float = 0.0
    error_reason: Optional[str] = None
    tokens: int = 0


class ModelExecutionTelemetry(BaseModel):
    model_selected: str = "none"
    provider: str = "none"
    fallback_occurred: bool = False
    fallback_reason: Optional[str] = None
    latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    attempts_count: int = 0
    attempt_history: List[ModelAttemptRecord] = Field(default_factory=list)


class ModelFallbackEngine:
    """
    Task 3 Model Fallback Engine supporting requirements extraction and capability checking.
    """

    def __init__(
        self,
        role: str = "REQUIREMENTS_EXTRACTION",
        gemini_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        anthropic_workspace_id: Optional[str] = None,
        max_attempts: Optional[int] = None,
        total_timeout_seconds: Optional[float] = None,
        request_timeout_seconds: Optional[float] = None,
        allow_preview_models: Optional[bool] = None,
    ):
        self.role = role
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY", "")
        self.anthropic_api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self.anthropic_workspace_id = anthropic_workspace_id or os.getenv("ANTHROPIC_WORKSPACE_ID", "")
        self.max_attempts = max_attempts if max_attempts is not None else int(os.getenv("MAX_FALLBACK_ATTEMPTS", "3"))
        self.total_timeout_seconds = total_timeout_seconds if total_timeout_seconds is not None else float(os.getenv("TOTAL_TIMEOUT_SECONDS", "15.0"))
        self.request_timeout_seconds = request_timeout_seconds if request_timeout_seconds is not None else float(os.getenv("REQUEST_TIMEOUT_SECONDS", "5.0"))
        if allow_preview_models is not None:
            self.allow_preview_models = allow_preview_models
        else:
            self.allow_preview_models = os.getenv("ALLOW_PREVIEW_MODELS", "false").lower() in ("true", "1", "yes")
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient()
        return self._client

    async def aclose(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def get_model_candidates(self) -> List[Tuple[str, str]]:
        primary_var, fallbacks_var = ROLE_ENV_VARS.get(self.role, ("MODEL_PRIMARY", "MODEL_FALLBACKS"))
        primary_model = os.getenv(primary_var, "").strip() or "gemini-3.5-flash"

        configured_fallbacks = os.getenv(fallbacks_var, "").strip()
        if configured_fallbacks:
            fallback_models = [m.strip() for m in configured_fallbacks.split(",") if m.strip()]
        else:
            fallback_models = [
                "claude-haiku-5-5",
                "gemini-3.1-flash-lite",
                "claude-sonnet-5-5",
                "gemini-3.5-flash-lite",
            ]
            if self.allow_preview_models:
                fallback_models.insert(1, "gemini-3-flash-preview")

        raw_list = [primary_model] + fallback_models
        candidates: List[Tuple[str, str]] = []
        seen = set()

        for idx, model in enumerate(raw_list):
            if not model or model in seen:
                continue
            seen.add(model)

            if model in DEPRECATED_MODELS and idx > 0:
                logger.warning("Excluding deprecated model '%s'", model)
                continue

            if "-preview" in model and not self.allow_preview_models and idx > 0:
                continue

            provider = "anthropic" if ("claude" in model.lower() or model.startswith("sk-ant-")) else "google"
            candidates.append((provider, model))

        return candidates

    def _is_non_retryable_provider_error(self, status_code: int, response_text: str) -> Tuple[bool, str]:
        lower_text = response_text.lower()
        if status_code in (401, 403):
            return True, f"Authentication/permission error (HTTP {status_code})"

        if status_code == 400:
            if "api key not valid" in lower_text or "api_key_invalid" in lower_text or "invalid x-api-key" in lower_text:
                return True, "API key is invalid or unrecognized"
            if "credit balance is too low" in lower_text or "plans & billing" in lower_text:
                return True, "Account billing credit exhausted"
            if "quota exceeded" in lower_text or "billing not enabled" in lower_text:
                return True, "Account billing/quota disabled"

        return False, ""

    def _is_quota_exhaustion_rate_limit(self, status_code: int, response_text: str) -> bool:
        if status_code == 429:
            lower = response_text.lower()
            if "resource_exhausted" in lower or "quota" in lower or "credit" in lower or "daily" in lower:
                return True
        return False

    async def execute_with_fallback(
        self,
        system_prompt: str,
        user_prompt: str,
        history: Optional[List[Dict[str, str]]] = None,
        max_tokens: int = 1500,
        temperature: float = 0.1,
        validate_fn: Optional[Callable[[str], Tuple[bool, Any, Optional[str]]]] = None,
    ) -> Tuple[Optional[str], Optional[Any], ModelExecutionTelemetry]:
        # Pre-warm client so SSL initialization is not counted against request deadlines
        await self._get_client()
        start_time = time.time()
        telemetry = ModelExecutionTelemetry()
        candidates = self.get_model_candidates()

        exhausted_providers: set[str] = set()
        invalid_credential_providers: set[str] = set()
        attempt_idx = 0

        for provider, model in candidates:
            if attempt_idx >= self.max_attempts:
                logger.warning("Reached maximum fallback attempts (%d). Aborting cascade.", self.max_attempts)
                telemetry.fallback_reason = telemetry.fallback_reason or f"Exceeded max attempts limit ({self.max_attempts})"
                break

            elapsed = time.time() - start_time
            if elapsed >= self.total_timeout_seconds:
                logger.warning("Total execution time (%.2fs) exceeded budget (%.2fs).", elapsed, self.total_timeout_seconds)
                telemetry.fallback_reason = telemetry.fallback_reason or f"Execution time exceeded deadline ({self.total_timeout_seconds}s)"
                break

            if provider in invalid_credential_providers or provider in exhausted_providers:
                continue

            if provider == "google" and (not self.gemini_api_key or self.gemini_api_key.startswith("sk-ant-")):
                continue
            if provider == "anthropic" and not self.anthropic_api_key:
                continue

            attempt_idx += 1
            telemetry.attempts_count = attempt_idx
            attempt_start = time.time()

            raw_text, http_code, err_msg, tokens = await self._call_model_with_transient_retry(
                provider=provider,
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                history=history,
                max_tokens=max_tokens,
                temperature=temperature,
                deadline=start_time + self.total_timeout_seconds
            )

            attempt_latency = (time.time() - attempt_start) * 1000.0

            attempt_rec = ModelAttemptRecord(
                model=model,
                provider=provider,
                status="SUCCESS" if raw_text else "FAILED",
                http_status=http_code,
                latency_ms=attempt_latency,
                error_reason=err_msg,
                tokens=tokens
            )
            telemetry.attempt_history.append(attempt_rec)

            if raw_text:
                if validate_fn:
                    is_valid, parsed_obj, val_err = validate_fn(raw_text)
                    if not is_valid:
                        logger.warning("Model '%s' output failed validation: %s. Falling back.", model, val_err)
                        telemetry.fallback_occurred = True
                        telemetry.fallback_reason = f"Structured validation failed: {val_err}"
                        attempt_rec.status = "VALIDATION_FAILED"
                        attempt_rec.error_reason = val_err
                        continue
                else:
                    parsed_obj = raw_text

                telemetry.model_selected = model
                telemetry.provider = provider
                telemetry.latency_ms = (time.time() - start_time) * 1000.0
                telemetry.total_tokens = tokens
                cost_rate = ESTIMATED_COST_PER_1K_TOKENS.get(model, 0.0001)
                telemetry.estimated_cost_usd = round((tokens / 1000.0) * cost_rate, 6)
                if attempt_idx > 1:
                    telemetry.fallback_occurred = True

                logger.info(
                    "Model executed: model=%s role=%s provider=%s latency=%.1fms fallback=%s",
                    model, self.role, provider, telemetry.latency_ms, telemetry.fallback_occurred
                )
                return raw_text, parsed_obj, telemetry

            telemetry.fallback_occurred = True
            telemetry.fallback_reason = telemetry.fallback_reason or f"Model '{model}' failed (HTTP {http_code}): {err_msg}"

            is_fatal, fatal_reason = self._is_non_retryable_provider_error(http_code or 0, err_msg or "")
            if is_fatal:
                logger.warning("Provider '%s' fatal error: %s. Aborting provider models.", provider, fatal_reason)
                invalid_credential_providers.add(provider)
                continue

            if self._is_quota_exhaustion_rate_limit(http_code or 0, err_msg or ""):
                logger.warning("Provider '%s' quota exhausted. Aborting provider models.", provider)
                exhausted_providers.add(provider)
                continue

        telemetry.model_selected = "deterministic_fallback"
        telemetry.provider = "deterministic"
        telemetry.latency_ms = (time.time() - start_time) * 1000.0
        return None, None, telemetry

    async def _call_model_with_transient_retry(
        self,
        provider: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        history: Optional[List[Dict[str, str]]],
        max_tokens: int,
        temperature: float,
        deadline: float,
    ) -> Tuple[Optional[str], Optional[int], Optional[str], int]:
        for retry in range(2):
            call_timeout = max(0.01, min(self.request_timeout_seconds, deadline - time.time()))
            if call_timeout <= 0.02:
                return None, 408, "Request budget deadline exceeded", 0

            try:
                if provider == "google":
                    coro = self._call_google_gemini(
                        model=model,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        history=history,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        timeout_seconds=call_timeout,
                    )
                else:
                    coro = self._call_anthropic_claude(
                        model=model,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        history=history,
                        max_tokens=max_tokens,
                        timeout_seconds=call_timeout,
                    )
                return await asyncio.wait_for(coro, timeout=call_timeout)
            except (asyncio.TimeoutError, httpx.TimeoutException) as net_err:
                if retry == 0 and (deadline - time.time()) > 1.5:
                    jitter = random.uniform(0.05, 0.15)
                    backoff = min(0.2 * (2 ** retry) + jitter, 0.5)
                    await asyncio.sleep(backoff)
                    continue
                return None, 408, f"Request timeout/deadline exceeded: {str(net_err)}", 0
            except httpx.NetworkError as net_err:
                if retry == 0 and (deadline - time.time()) > 1.5:
                    jitter = random.uniform(0.05, 0.15)
                    backoff = min(0.2 * (2 ** retry) + jitter, 0.5)
                    await asyncio.sleep(backoff)
                    continue
                return None, 503, f"Network communication error: {str(net_err)}", 0
            except Exception as exc:
                return None, 500, f"Unexpected error: {str(exc)}", 0

        return None, 500, "Transient retry exhausted", 0

    async def _call_google_gemini(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        history: Optional[List[Dict[str, str]]],
        max_tokens: int,
        temperature: float,
        timeout_seconds: float,
    ) -> Tuple[Optional[str], int, Optional[str], int]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.gemini_api_key}"
        contents = [{"role": "user", "parts": [{"text": user_prompt}]}]

        payload = {
            "contents": contents,
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens
            }
        }

        client = await self._get_client()
        res = await client.post(url, json=payload, timeout=timeout_seconds)
        http_status = res.status_code

        if http_status == 200:
            data = res.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    text = parts[0].get("text", "").strip()
                    usage = data.get("usageMetadata", {})
                    total_tok = usage.get("totalTokenCount", len(text.split()) * 2)
                    return text, 200, None, total_tok
            if "content" in data and isinstance(data["content"], list) and len(data["content"]) > 0:
                text = data["content"][0].get("text", "").strip()
                return text, 200, None, len(text.split()) * 2
            return None, 200, "Empty candidates array in response", 0

        return None, http_status, res.text[:240], 0

    async def _call_anthropic_claude(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        history: Optional[List[Dict[str, str]]],
        max_tokens: int,
        timeout_seconds: float,
    ) -> Tuple[Optional[str], int, Optional[str], int]:
        headers = {
            "x-api-key": self.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        if self.anthropic_workspace_id:
            headers["anthropic-workspace-id"] = self.anthropic_workspace_id

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }

        client = await self._get_client()
        res = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=timeout_seconds)
        http_status = res.status_code

        if http_status == 200:
            data = res.json()
            content = data.get("content", [])
            if content:
                text = content[0].get("text", "").strip()
                usage = data.get("usage", {})
                tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                return text, 200, None, tokens
            return None, 200, "Empty content array in response", 0

        return None, http_status, res.text[:240], 0
