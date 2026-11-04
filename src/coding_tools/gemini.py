# src/coding_tools/gemini.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
#

"""Google GenAI wrapper meeting LLMClientProtocol.

Ties into google-genai v2. Needs API key. Handles structured output and retry.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import TYPE_CHECKING, Any, TypeVar, cast

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from coding_tools import conf, llm_protocol, my_io, my_logger, my_string
from coding_tools.llm_protocol import LLMAPIError, LLMClientError, LLMServerError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

DEFAULT_MODEL = "gemini-3.5-flash-lite"
HTTP_SERVICE_UNAVAILABLE = 503
RESOURCE_EXHAUSTED = 429
MAX_RETRIES = 3
MAX_REQUESTS_PER_MINUTE = 14
WINDOW_SECONDS = 60.0

CALL_TIMESTAMPS: deque[float] = deque()
RATE_LIMIT_LOCK = asyncio.Lock()

T = TypeVar("T", bound=BaseModel)


logger = my_logger.logger(__name__)


def _max_requests_per_minute() -> int:
    return MAX_REQUESTS_PER_MINUTE


def _max_retries() -> int:
    return MAX_RETRIES


def _resource_exhausted() -> int:
    return RESOURCE_EXHAUSTED


def clean_old_timestamps(
    timestamps: deque[float],
    now: float,
    window: float = WINDOW_SECONDS,
) -> None:
    """Remove timestamps older than the sliding window."""
    while timestamps and timestamps[0] < now - window:
        timestamps.popleft()


def _should_sleep(
    now: float,
) -> tuple[bool, float]:
    """Compute required sleep duration to respect rate limits."""
    condition = False
    sleep_time = 0.0
    if CALL_TIMESTAMPS:
        sleep_time = CALL_TIMESTAMPS[0] + WINDOW_SECONDS - now
        if sleep_time > 0 and len(CALL_TIMESTAMPS) >= _max_requests_per_minute():
            condition = True
    return condition, sleep_time


def should_retry(
    status_code: int | None,
    current_try: int,
    max_retries: int = MAX_RETRIES,
) -> tuple[bool, float]:
    """Determine if a request should be retried based on status and try count."""
    condition = (
        status_code == HTTP_SERVICE_UNAVAILABLE and current_try < max_retries - 1
    )
    if condition:
        sleep_time = (2**current_try) * 2
        return condition, sleep_time
    return False, 0.0


async def _rate_limit_throttle(
    time_func: Callable[[], float] = time.time,
    sleep_func: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> None:
    """Throttle calls to stay under free tier limits.

    Check timestamp deque, sleep if limit hit, add now. Uses async lock.
    """
    async with RATE_LIMIT_LOCK:
        now = time_func()
        clean_old_timestamps(CALL_TIMESTAMPS, now)
        sleep, sleep_time = _should_sleep(now)
        if sleep:
            await sleep_func(sleep_time)
        CALL_TIMESTAMPS.append(time_func())


def set_config(
    response_schema: type[BaseModel],
) -> dict[str, object]:
    """Build config dict for GenAI run.

    Set mime type to json, low think config, disable tool use.
    """
    config_kwargs: dict[str, object] = {
        "thinking_config": types.ThinkingConfig(
            thinking_level=types.ThinkingLevel.LOW,
        ),
        "response_mime_type": "application/json",
        "response_schema": response_schema,
        "tools": None,
        "automatic_function_calling": types.AutomaticFunctionCallingConfig(
            disable=True,
        ),
    }

    return config_kwargs


async def llm_call(
    client: genai.Client,
    req: str,
    model: str,
    config: dict[str, object],
    prefix: str | None = None,
) -> object:
    """Call LLM API and get parsed response.

    Catch server, client, and API errors, map to custom types. Needs API key.
    """
    await _rate_limit_throttle()
    resp: genai.types.GenerateContentResponse | None = None
    try:
        with logger.run_spin("Call LLM", my_string.my_str(prefix)):
            resp = client.models.generate_content(
                model=model,
                contents=req,
                config=types.GenerateContentConfig(
                    **dict[str, Any](config),
                ),
            )
    except genai.errors.ServerError as e:
        if e.code == HTTP_SERVICE_UNAVAILABLE:
            this_msg = "Failed. HTTP 503"
            logger.exception(
                prefix,
                this_msg,
            )
        msg = getattr(e, "message", None) or str(e)
        raise LLMServerError(
            message=msg,
            status_code=getattr(e, "code", None),
            retryable=(e.code == HTTP_SERVICE_UNAVAILABLE),
        ) from e
    except genai.errors.ClientError as e:
        if e.code == _resource_exhausted():
            this_msg = "Failed. 429 RESOURCE_EXHAUSTED"
            logger.exception(
                prefix,
                this_msg,
            )
        msg = getattr(e, "message", None) or str(e)
        raise LLMClientError(
            message=msg,
            status_code=getattr(e, "code", None),
        ) from e
    except (genai.errors.APIError, Exception) as e:
        this_msg = "Failed Gemini API exchanges"
        msg = getattr(e, "message", None) or str(e) or this_msg
        logger.exception(prefix, this_msg)
        raise LLMAPIError(
            message=msg,
            status_code=getattr(e, "code", None),
            error_code=getattr(e, "status", None),
        ) from e

    return resp.parsed


class RetryParams(BaseModel):
    """Parameters for retry_llm_call."""
    client: Any
    req: str
    model: str
    config: dict[str, object]
    prefix: str | None = None
    sleep_func: Callable[[float], Awaitable[Any]] = asyncio.sleep


async def retry_llm_call(
    params: RetryParams,
) -> object | None:
    """Call LLM with 503 retry logic.

    Retry up to 3 times with exponential backoff. Raise LLMServerError if fail.
    """
    resp: Any | None = None
    for _try in range(_max_retries()):
        try:
            resp = await llm_call(
                params.client,
                params.req,
                params.model,
                params.config,
                params.prefix,
            )
        except LLMServerError as e:
            retry, sleep_time = should_retry(e.status_code, _try)
            if retry:
                logger.warning(
                    params.prefix,
                    f"Bad reply http 503. Retry in {sleep_time}s "
                    f"(Try {_try + 1}/{_max_retries()})...",
                )
                await params.sleep_func(sleep_time)
                continue
            logger.exception(params.prefix, "Failed tries to bypass http 503")
            raise
        except (LLMAPIError, LLMClientError, Exception):
            logger.exception(params.prefix, "Failed LLM API exchanges")
            raise
        else:
            break
    return resp


def _raise_schema_error(schema_name: str) -> None:
    """Raise ValueError for schema check fail."""
    msg = f"GenAI response did not conform to {schema_name} schema."
    raise ValueError(msg)


class Gemini:
    """Google GenAI wrapper meeting LLMClientProtocol.

    Needs API key. Handles structured gen and retry logic.
    """

    def __init__(self, model_name: str | None = None) -> None:
        """Set up client with model name or default conf."""
        self.client = genai.Client()
        if model_name is not None:
            self.model_name = model_name
        else:
            gemini_conf = conf.get_provider_mapping().get("gemini", {})
            self.model_name = str(
                gemini_conf.get("default_model", DEFAULT_MODEL),
            )

    async def call(
        self,
        req: str,
        params: llm_protocol.LLMCallParams,
    ) -> llm_protocol.LLMResponse:
        """Get Pydantic model response from GenAI API.

        Raise ValueError if schema check fail. Save request and response log.
        """
        config_kwargs = set_config(
            response_schema=params.response_schema,
        )

        resp = await retry_llm_call(
            RetryParams(
                client=self.client,
                req=req,
                model=self.model_name,
                config=config_kwargs,
                prefix=params.prefix,
            ),
        )

        if resp is None:
            _raise_schema_error(params.response_schema.__name__)

        try:
            checked_obj = params.response_schema.model_validate(resp)
        except ValidationError:
            _raise_schema_error(params.response_schema.__name__)
            raise

        my_io.save_llm_req_resp(
            func=params.tool_name,
            llm=self.model_name,
            request=req,
            response=str(resp),
            target_file=params.target_file,
        )

        return cast("llm_protocol.LLMResponse", checked_obj)
