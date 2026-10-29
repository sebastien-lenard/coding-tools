# src/coding_tools/gemini.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
#

"""Google GenAI wrapper meeting LLMClientProtocol.

Ties into google-genai v2. Needs API key.
Handles formatted writing and context caching.
"""

from __future__ import annotations

import time
from typing import Any, TypeVar, cast

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from coding_tools import config, llm_protocol, my_io, my_logger
from coding_tools.llm_protocol import LLMAPIError, LLMServerError

DEFAULT_MODEL = "gemini-3.5-flash-lite"
HTTP_SERVICE_UNAVAILABLE = 503
MAX_RETRIES = 3

T = TypeVar("T", bound=BaseModel)


logger = my_logger.logger(__name__)


def set_config(
    response_schema: type[BaseModel],
) -> dict[str, object]:
    """Build config dict for structured GenAI execution.

    Sets response mime type to application/json and blocks function calling.
    config_kwargs will contain the model name, thinking level,
    the pydantic validation schema for the LLM response (message / code).
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


def llm_call(
    client: genai.Client,
    req: str,
    model: str,
    config: dict[str, object],
    prefix: str | None = None,
) -> object:
    """Call Gemini with request (prompt) and get Gemini response.

    Handles Gemini errors by re-raising llm-neutral LLMServerError or others.
    """
    resp: genai.types.GenerateContentResponse | None = None
    try:
        with logger.run_spin("Call LLM", str(prefix)):
            resp = client.models.generate_content(
                model=model,
                contents=req,
                config=types.GenerateContentConfig(
                    **dict[str, Any](config),
                ),
            )
    except genai.ServerError as e:
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
    except (errors.APIError, Exception) as e:
        this_msg = "Failed Gemini API exchanges"
        msg = getattr(e, "message", None) or str(e) or this_msg
        logger.exception(prefix, this_msg)
        raise LLMAPIError(
            message=msg,
            status_code=getattr(e, "code", None),
            error_code=getattr(e, "status", None),
        ) from e

    return resp.parsed


def retry_llm_call(
    client: genai.Client,
    req: str,
    model: str,
    config: dict[str, object],
    prefix: str | None = None,
) -> object:
    """Call llm with retry logic.

    503 retry up to 3 times with exponential backoff. Raise LLMServerError if persist.
    """
    resp: Any | None = None
    for _try in range(MAX_RETRIES):
        try:
            resp = llm_call(client, req, model, config, prefix)
        except LLMServerError as e:
            if e.status_code == HTTP_SERVICE_UNAVAILABLE and _try < MAX_RETRIES - 1:
                sleep_time = (2**_try) * 2
                logger.warning(
                    prefix,
                    f"Bad reply http 503. Retry in {sleep_time}s "
                    f"(Try {_try + 1}/{MAX_RETRIES})...",
                )
                time.sleep(sleep_time)
                continue
            this_msg = "Failed tries to bypass http 503"
            logger.exception(
                prefix,
                this_msg,
            )
            raise
        except (LLMAPIError, Exception) as e:
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
    """Raise ValueError for schema conformance failure."""
    msg = f"GenAI response did not conform to {schema_name} schema."
    raise ValueError(msg)


class Gemini:
    """Google GenAI wrapper meeting LLMClientProtocol.

    Needs API key. Handles structured generation and context caching.
    """

    def __init__(self, model_name: str | None = None) -> None:
        """Init client with model name or default provider config."""
        self.client = genai.Client()
        if model_name is not None:
            self.model_name = model_name
        else:
            gemini_config = config.get_provider_mapping().get("gemini", {})
            self.model_name = str(
                gemini_config.get("default_model", DEFAULT_MODEL),
            )

    def call(
        self,
        req: str,
        params: llm_protocol.LLMCallParams,
    ) -> llm_protocol.LLMResponse:
        """Get validated Pydantic model response from GenAI API.

        Raise ValueError if response does not conform to schema.
        """
        config_kwargs = set_config(
            response_schema=params.response_schema,
        )

        exception_to_raise: Exception | None = None
        checked_obj: BaseModel = params.response_schema(message="", edited_files="")
        resp = None
        try:
            resp = retry_llm_call(
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
        except (LLMServerError, LLMAPIError) as e:
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
