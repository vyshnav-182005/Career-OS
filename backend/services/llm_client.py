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

Clients are cached per (timeout, max_retries) rather than constructed per call.
An OpenAI client owns an httpx connection pool, so building a new one for every
request threw the pool away each time and paid a fresh TLS handshake to
integrate.api.nvidia.com - which the job-matching fan-out did seven times per
/jobs/recommended. Both client types are safe to share: httpx.Client is
thread-safe, and the async pool is keyed by event loop below so a client is
never reused across a loop it wasn't created on.
"""

from __future__ import annotations

import asyncio
import threading

from openai import AsyncOpenAI, OpenAI

from backend.config import settings

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

# Pass as `extra_body=NO_THINKING` on chat.completions.create.
NO_THINKING = {"chat_template_kwargs": {"thinking": False}}

_sync_lock = threading.Lock()
_sync_clients: dict[tuple[float, int], OpenAI] = {}
# Keyed by (loop id, timeout, max_retries): an httpx.AsyncClient binds to the
# loop that created it, so a client built under asyncio.run() in one script
# must not be handed to a later loop. Guarded by the same lock, which is only
# ever held for a dict lookup.
_async_clients: dict[tuple[int, float, int], AsyncOpenAI] = {}


def build_client(timeout: float = 60.0, max_retries: int = 1) -> OpenAI:
    """Returns the shared blocking client for this (timeout, max_retries)."""
    key = (timeout, max_retries)
    with _sync_lock:
        client = _sync_clients.get(key)
        if client is None:
            client = OpenAI(
                base_url=NVIDIA_BASE_URL,
                api_key=settings.nvidia_api_key,
                timeout=timeout,
                max_retries=max_retries,
            )
            _sync_clients[key] = client
        return client


def build_async_client(timeout: float = 60.0, max_retries: int = 1) -> AsyncOpenAI:
    """
    Returns the shared async client for this (timeout, max_retries) on the
    running event loop. Prefer this over build_client anywhere the call is
    awaited: a blocking client parked in a worker thread cannot be cancelled,
    so a timeout around it abandons the caller while the request runs on.
    """
    try:
        loop_key = id(asyncio.get_running_loop())
    except RuntimeError:
        # No running loop (constructed eagerly at import, say). Don't cache -
        # we can't tell which loop will end up owning the connection pool.
        return AsyncOpenAI(
            base_url=NVIDIA_BASE_URL,
            api_key=settings.nvidia_api_key,
            timeout=timeout,
            max_retries=max_retries,
        )

    key = (loop_key, timeout, max_retries)
    with _sync_lock:
        client = _async_clients.get(key)
        if client is None:
            client = AsyncOpenAI(
                base_url=NVIDIA_BASE_URL,
                api_key=settings.nvidia_api_key,
                timeout=timeout,
                max_retries=max_retries,
            )
            _async_clients[key] = client
        return client
