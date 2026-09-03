"""
Provider registry.

Which sources a deployment ingests from is configuration, not code: set
JOB_PROVIDERS in backend/.env to a comma-separated list of provider names.

    JOB_PROVIDERS=jooble,greenhouse,lever

Providers whose credentials are missing are skipped with a log line rather than
failing the run, so enabling `adzuna` before you've obtained keys is harmless.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, List

from backend.config import settings
from backend.services.job_providers.base import BaseJobProvider
from backend.services.job_providers.adzuna_provider import AdzunaProvider
from backend.services.job_providers.greenhouse_provider import GreenhouseProvider
from backend.services.job_providers.jooble_provider import JoobleProvider
from backend.services.job_providers.lever_provider import LeverProvider

logger = logging.getLogger(__name__)

PROVIDER_FACTORIES: Dict[str, Callable[[], BaseJobProvider]] = {
    "jooble": JoobleProvider,
    "adzuna": AdzunaProvider,
    "greenhouse": GreenhouseProvider,
    "lever": LeverProvider,
}


def build_providers() -> List[BaseJobProvider]:
    """
    Instantiates the providers named in JOB_PROVIDERS, in order. Unknown names
    are logged and skipped so a typo degrades ingestion instead of breaking
    startup.
    """
    names = [name.strip().lower() for name in (settings.job_providers or "").split(",") if name.strip()]
    providers: List[BaseJobProvider] = []

    for name in names:
        factory = PROVIDER_FACTORIES.get(name)
        if not factory:
            logger.warning("Unknown job provider '%s' in JOB_PROVIDERS; known: %s", name, ", ".join(PROVIDER_FACTORIES))
            continue
        providers.append(factory())

    if not providers:
        logger.warning("JOB_PROVIDERS resolved to no usable providers - falling back to Jooble.")
        providers.append(JoobleProvider())

    logger.info("Job providers enabled: %s", ", ".join(p.provider_name for p in providers))
    return providers
