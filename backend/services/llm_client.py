"""
Shared construction of the NVIDIA NIM chat client.

Every agent talks to the same endpoint with the same credentials, so the
base_url/api_key pair lives here rather than being restated at each call site.

The other thing this centralizes is `NO_THINKING`. The models NVIDIA currently
serves are reasoning models: left to themselves they emit a chain-of-thought
preamble into `message.content` before the answer. Every one of our call sites
wants only the answer - most parse the content as JSON, and
github_enrichment caps the response at 150 tokens, which a reasoning preamble
would consume entirely. Disabling thinking also cuts job-matching latency
roughly 4x (measured: ~18s -> ~4s per batch), which is what keeps the
/jobs/recommended request path inside its timeout budget.

`chat_template_kwargs.thinking` is passed through `extra_body`; a model that
doesn't recognize the key ignores it, so this is safe across model changes.
"""

from __future__ import annotations

from openai import AsyncOpenAI, OpenAI

from backend.config import settings

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

# Pass as `extra_body=NO_THINKING` on chat.completions.create.
NO_THINKING = {"chat_template_kwargs": {"thinking": False}}


def build_client(timeout: float = 60.0, max_retries: int = 1) -> OpenAI:
    return OpenAI(
        base_url=NVIDIA_BASE_URL,
        api_key=settings.nvidia_api_key,
        timeout=timeout,
        max_retries=max_retries,
    )


def build_async_client(timeout: float = 60.0, max_retries: int = 1) -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=NVIDIA_BASE_URL,
        api_key=settings.nvidia_api_key,
        timeout=timeout,
        max_retries=max_retries,
    )
