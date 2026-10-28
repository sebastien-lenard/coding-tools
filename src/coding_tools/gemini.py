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
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar, cast

from google.genai import Client, errors, types
from google.genai.errors import ServerError
from pydantic import BaseModel

from coding_tools import config, my_logger
from coding_tools.config import is_caching_allowed
from coding_tools.file_handler import (
    get_conftest_path,
    get_pyproject_path,
)
from coding_tools.llm_persistence import PersistOutputParameters, persist_llm_output
from coding_tools.llm_prompts import load_skill
from coding_tools.llm_protocol import LLMAPIError, LLMServerError

if TYPE_CHECKING:
    from google.genai.types import File

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


def upload_static_file(client: Client, file_path: str | Path, prefix: str) -> File:
    """Upload static ref file to Gemini API.

    Needs API key and valid file path. Raise LLMAPIError on failure.
    """
    path = Path(file_path)
    logger.progress(prefix, f"Upload static ref file: {path.name}")
    try:
        return client.files.upload(
            file=str(path),
            config=types.UploadFileConfig(mime_type="text/plain"),
        )
    except (errors.APIError, Exception) as e:
        msg = getattr(e, "message", None) or str(e) or "Failed upload to Gemini"
        logger.exception(path, "Failed upload of static ref file to Gemini")
        raise LLMAPIError(
            message=msg,
            status_code=getattr(e, "code", None),
            error_code=getattr(e, "status", None),
        ) from e


def validate_file_uris(
    file_config: File,
    file_conftest: File,
    file_source: File,
) -> tuple[str, str, str]:
    """Check uploaded file URIs are not None.

    Raise ValueError if any URI is None.
    """
    if file_config.uri is None or file_conftest.uri is None or file_source.uri is None:
        msg = "Bad URIs of uploaded file(s)"
        logger.error(None, msg)
        raise ValueError(msg)
    return file_config.uri, file_conftest.uri, file_source.uri


def build_config(
    response_schema: type[BaseModel],
    system_instruction: str | None = None,
    cache_name: str | None = None,
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

    if is_caching_allowed("gemini") and cache_name is not None:
        config_kwargs["cached_content"] = cache_name
    elif system_instruction is not None:
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

    @property
    def supports_caching(self) -> bool:
        """Get cache support status from config."""
        return is_caching_allowed("gemini")

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
            cache_name=options.cache_name,
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
                supports_caching=self.supports_caching,
            ),
        )

        if exception_to_raise is not None:
            raise exception_to_raise

        return validated_obj

    def setup_cache(
        self,
        source_file_path: str,
        prefix: str,
    ) -> tuple[str | None, list[object]]:
        """Upload reference files and create context cache if enabled.

        Needs API key. Return cache name and uploaded files list.
        """
        uploaded_files: list[File | None] = []
        if not self.supports_caching:
            return None, uploaded_files  # type: ignore[return-value]

        pyproject_path = get_pyproject_path(source_file_path)
        conftest_path = get_conftest_path(source_file_path)

        logger.progress(prefix, "Caching enabled. Uploading static reference files...")
        file_config = upload_static_file(self.client, pyproject_path, prefix)
        file_conftest = upload_static_file(self.client, conftest_path, prefix)
        file_source = upload_static_file(self.client, source_file_path, prefix)
        uploaded_files.extend([file_config, file_conftest, file_source])

        config_uri, conftest_uri, source_uri = validate_file_uris(
            file_config,
            file_conftest,
            file_source,
        )

        logger.progress(prefix, "Creating context cache...")
        try:
            cached_content = self.client.caches.create(
                model=self.model_name,
                config=types.CreateCachedContentConfig(
                    display_name=f"unit-test-context-{prefix}",
                    ttl="3600s",
                    contents=[
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_uri(
                                    file_uri=source_uri,
                                    mime_type="text/plain",
                                ),
                                types.Part.from_uri(
                                    file_uri=config_uri,
                                    mime_type="text/plain",
                                ),
                                types.Part.from_uri(
                                    file_uri=conftest_uri,
                                    mime_type="text/plain",
                                ),
                            ],
                        ),
                    ],
                    system_instruction=load_skill("fix_unit_test.md"),
                ),
            )
        except (errors.APIError, Exception) as e:
            msg = (
                getattr(e, "message", None)
                or str(e)
                or "Unknown Gemini API error during cache creation"
            )
            logger.exception(prefix, "Failed to create context cache")
            raise LLMAPIError(
                message=msg,
                status_code=getattr(e, "code", None),
                error_code=getattr(e, "status", None),
            ) from e
        return cached_content.name, uploaded_files  # type: ignore[return-value]

    def cleanup_files(self, files: list[object], prefix: str) -> None:
        """Delete remote uploaded static files from Gemini API.

        Log warning on API error.
        """
        logger.progress(prefix, "Cleaning up remote uploaded static files...")
        for f in files:
            if f is not None and hasattr(f, "name"):
                try:
                    file_name = cast("Any", f).name
                    self.client.files.delete(name=file_name)
                except (errors.APIError, Exception) as e:  # noqa: BLE001
                    logger.warning(
                        prefix,
                        f"Failed to delete remote file: "
                        f"{getattr(e, 'message', None) or str(e) or 'Unknown error'}",
                    )
