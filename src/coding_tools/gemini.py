# src/coding_tools/gemini.py
# SPDX-FileCopyrightText: 2026 Sebastien Lenard <sebastien.lenard@gmail.com> and Contributors
# SPDX-License-Identifier: Apache-2.0
#

"""Google GenAI wrapper meeting LLMClientProtocol.

Ties into google-genai v2. Needs API key.
Handles formatted writing and context caching.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar, cast

from google.genai import Client, errors, types
from google.genai.errors import ServerError
from pydantic import BaseModel

from coding_tools import config, my_logger
from coding_tools.llm_persistence import PersistOutputParameters, persist_llm_output
from coding_tools.llm_protocol import LLMAPIError, LLMServerError

if TYPE_CHECKING:
    from coding_tools.llm_protocol import StructuredGenerationOptions

HTTP_SERVICE_UNAVAILABLE = 503

T = TypeVar("T", bound=BaseModel)


logger = my_logger.logger(__name__)


@dataclass
class RetryRequestParameters:
    """Store params for Gemini API runs.

    Holds client, model name, contents list, config kwargs, prefix, and spinner msg.
    """

    client: Client
    model_name: str
    contents_list: list[types.ContentUnion]
    config_kwargs: dict[str, object]
    prefix: str
    spinner_msg: str


def build_config(
    response_schema: type[BaseModel],
    system_instruction: str | None = None,
) -> dict[str, object]:
    """Build config dict for structured GenAI execution.

    Sets response mime type to application/json and blocks function calling.
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

    if system_instruction is not None:
        config_kwargs["system_instruction"] = system_instruction

    return config_kwargs


def call_gemini_with_retry(
    params: RetryRequestParameters,
) -> types.GenerateContentResponse:
    """Run Gemini generate_content call with ServerError retry logic.

    503 retry up to 3 times with exponential backoff. Raise LLMServerError if persist.
    """
    max_retries = 3
    response: types.GenerateContentResponse | None = None
    for attempt in range(max_retries):
        try:
            with logger.run_spin(params.spinner_msg, params.prefix):
                response = params.client.models.generate_content(
                    model=params.model_name,
                    contents=params.contents_list,
                    config=types.GenerateContentConfig(
                        **dict[str, Any](params.config_kwargs),
                    ),
                )
        except ServerError as e:
            if e.code == HTTP_SERVICE_UNAVAILABLE and attempt < max_retries - 1:
                sleep_time = (2**attempt) * 2
                logger.warning(
                    params.prefix,
                    f"Bad reply http 503. Retry in {sleep_time}s "
                    f"(Try {attempt + 1}/{max_retries})...",
                )
                time.sleep(sleep_time)
                continue
            this_msg = "Failed tries to bypass http 503"
            logger.exception(
                params.prefix,
                this_msg,
            )
            msg = getattr(e, "message", None) or str(e) or this_msg
            raise LLMServerError(
                message=msg,
                status_code=getattr(e, "code", None),
                retryable=(e.code == HTTP_SERVICE_UNAVAILABLE),
            ) from e
        except (errors.APIError, Exception) as e:
            this_msg = "Failed Gemini API exchanges"
            msg = getattr(e, "message", None) or str(e) or this_msg
            logger.exception(params.prefix, this_msg)
            raise LLMAPIError(
                message=msg,
                status_code=getattr(e, "code", None),
                error_code=getattr(e, "status", None),
            ) from e
        else:
            break

    if response is None:
        msg = "Failed to generate content after max retries due to server errors."
        logger.error(params.prefix, msg)
        raise LLMServerError(
            message=msg,
            status_code=HTTP_SERVICE_UNAVAILABLE,
            retryable=False,
        )
    return response


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
        self.client = Client()
        if model_name is not None:
            self.model_name = model_name
        else:
            gemini_config = config.get_provider_mapping().get("gemini", {})
            self.model_name = str(
                gemini_config.get("default_model", "gemini-3.5-flash-lite"),
            )

    def response(
        self,
        contents_list: list[object],
        options: StructuredGenerationOptions,
    ) -> BaseModel:
        """Get validated Pydantic model response from GenAI API.

        Raise ValueError if response does not conform to schema.
        """
        config_kwargs = build_config(
            response_schema=options.response_schema,
            system_instruction=options.system_instruction,
        )

        gemini_contents: list[types.ContentUnion] = [
            types.Part.from_text(text=str(item)) for item in contents_list
        ]

        params = RetryRequestParameters(
            client=self.client,
            model_name=self.model_name,
            contents_list=gemini_contents,
            config_kwargs=config_kwargs,
            prefix=options.prefix,
            spinner_msg=options.spinner_msg,
        )

        status_label = "ok"
        error_details: str | None = None
        raw_text: str | None = None
        parsed_json: Any | None = None
        parsed_model: BaseModel | None = None
        exception_to_raise: Exception | None = None
        validated_obj: BaseModel = options.response_schema(message="", code="")

        try:
            response = call_gemini_with_retry(params)
            raw_text = response.text
            if raw_text:
                try:
                    parsed_json = json.loads(raw_text)
                except json.JSONDecodeError:
                    parsed_json = None

            parsed = response.parsed
            if parsed is None:
                status_label = "ko"
                schema_name = options.response_schema.__name__
                error_details = (
                    f"GenAI response did not conform to {schema_name} schema."
                )
                _raise_schema_error(schema_name)

            parsed_model = cast("BaseModel", parsed)
            validated_obj = options.response_schema.model_validate(parsed)
        except (LLMServerError, LLMAPIError) as e:
            status_label = (
                "503"
                if getattr(e, "status_code", None) == HTTP_SERVICE_UNAVAILABLE
                else "ko"
            )
            error_details = str(e)
            exception_to_raise = e
        except ValueError as e:
            status_label = "ko"
            error_details = str(e)
            exception_to_raise = e
        except (TypeError, AttributeError, RuntimeError) as e:
            status_label = "ko"
            error_details = str(e)
            exception_to_raise = e
        else:
            exception_to_raise = None

        persist_llm_output(
            PersistOutputParameters(
                options=options,
                status_label=status_label,
                raw_text=raw_text,
                parsed_json=parsed_json,
                parsed_model=parsed_model,
                error_details=error_details,
                contents_list=contents_list,
                model_name=self.model_name,
            ),
        )

        if exception_to_raise is not None:
            raise exception_to_raise

        return validated_obj
