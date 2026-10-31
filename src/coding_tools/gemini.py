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
from typing import Any, TypeVar, cast

from google import genai
from google.genai import types
from pydantic import BaseModel

from coding_tools import conf, llm_protocol, my_io, my_logger, my_string
from coding_tools.llm_protocol import LLMAPIError, LLMClientError, LLMServerError

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


async def _rate_limit_throttle() -> None:
    """Throttle calls to stay under free tier limits.

    Check timestamp deque, sleep if limit hit, add now.
    """
    async with RATE_LIMIT_LOCK:
        now = time.time()
        while CALL_TIMESTAMPS and CALL_TIMESTAMPS[0] < now - WINDOW_SECONDS:
            CALL_TIMESTAMPS.popleft()
        if len(CALL_TIMESTAMPS) >= MAX_REQUESTS_PER_MINUTE:
            sleep_time = CALL_TIMESTAMPS[0] + WINDOW_SECONDS - now
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
        CALL_TIMESTAMPS.append(time.time())


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

    Catch server, client, and API errors, map to custom types.
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
        if e.code == RESOURCE_EXHAUSTED:
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


async def retry_llm_call(
    client: genai.Client,
    req: str,
    model: str,
    config: dict[str, object],
    prefix: str | None = None,
) -> object:
    """Call LLM with 503 retry logic.

    Retry up to 3 times with exponential backoff. Raise LLMServerError if fail.
    """
    resp: Any | None = None
    for _try in range(MAX_RETRIES):
        try:
            resp = await llm_call(client, req, model, config, prefix)
        except LLMServerError as e:
            if e.status_code == HTTP_SERVICE_UNAVAILABLE and _try < MAX_RETRIES - 1:
                sleep_time = (2**_try) * 2
                logger.warning(
                    prefix,
                    f"Bad reply http 503. Retry in {sleep_time}s "
                    f"(Try {_try + 1}/{MAX_RETRIES})...",
                )
                await asyncio.sleep(sleep_time)
                continue
            this_msg = "Failed tries to bypass http 503"
            logger.exception(
                prefix,
                this_msg,
            )
            raise
        except (LLMAPIError, LLMClientError, Exception) as e:
            this_msg = "Failed LLM API exchanges"
            msg = getattr(e, "message", None) or str(e) or this_msg
            logger.exception(prefix, this_msg)
            raise
        else:
            break

    if not resp:
        msg = (
            f"Failed to get llm edits content after {MAX_RETRIES} retries "
            f"due to server or API errors."
        )
        logger.error(prefix, msg)
        raise LLMServerError(
            message=msg,
            status_code=HTTP_SERVICE_UNAVAILABLE,
            retryable=False,
        )
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

        exception_to_raise: Exception | None = None
        checked_obj: BaseModel = params.response_schema(message="", edited_files="")
        resp = None
        try:
            resp = await retry_llm_call(
                client=self.client,
                req=req,
                model=self.model_name,
                config=config_kwargs,
                prefix=params.prefix,
            )

            if resp is None:
                schema_name = params.response_schema.__name__
                _raise_schema_error(schema_name)
            checked_obj = params.response_schema.model_validate(resp)
        except (LLMServerError, LLMAPIError, LLMClientError) as e:
            exception_to_raise = e
        except ValueError as e:
            exception_to_raise = e
        except (TypeError, AttributeError, RuntimeError) as e:
            exception_to_raise = e
        else:
            exception_to_raise = None
        if resp:
            my_io.save_llm_req_resp(
                func=params.tool_name,
                llm=self.model_name,
                request=req,
                response=str(resp),
                target_file=params.target_file,
            )

        if exception_to_raise is not None:
            raise exception_to_raise

        return cast("llm_protocol.LLMResponse", checked_obj)
