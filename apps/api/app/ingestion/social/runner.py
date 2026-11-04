"""Running an Apify Actor and reading its rows (the only module that talks to Apify).

Cost controls live here and in the Actor input: a hard run timeout, a spend ceiling Apify
enforces (``max_total_charge_usd``), and a cap on rows (``max_items``). No row is persisted
from here; callers receive plain dicts.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Any, Protocol

log = logging.getLogger(__name__)


class ActorRunError(Exception):
    """The Actor did not finish successfully. The message is safe to store."""


class ActorRunner(Protocol):
    def run(
        self, actor_id: str, run_input: dict[str, Any], *, max_items: int, timeout_seconds: int, max_charge_usd: float
    ) -> list[dict[str, Any]]: ...


def apify_actor_path(actor_id: str) -> str:
    """``owner/name`` -> ``owner~name`` (the form the REST API uses)."""
    return actor_id.strip().replace("/", "~")


class ApifyActorRunner:
    def __init__(self, token: str) -> None:
        if not token:
            raise ValueError("an Apify API token is required")
        from apify_client import ApifyClient  # imported lazily: tests and RSS-only installs never need it

        self._client = ApifyClient(token)

    def run(
        self, actor_id: str, run_input: dict[str, Any], *, max_items: int, timeout_seconds: int, max_charge_usd: float
    ) -> list[dict[str, Any]]:
        run = self._client.actor(apify_actor_path(actor_id)).call(
            run_input=run_input,
            max_items=max_items,
            max_total_charge_usd=Decimal(str(max_charge_usd)),
            run_timeout=timedelta(seconds=timeout_seconds),
            wait_duration=timedelta(seconds=timeout_seconds + 60),
            logger=None,
        )
        if run is None:
            raise ActorRunError("Apify did not return a run (it may not have finished in time)")
        if run.status != "SUCCEEDED":
            raise ActorRunError(f"Actor run {run.id} ended with status {run.status}")
        rows = list(self._client.dataset(run.default_dataset_id).iterate_items(limit=max_items + 20))
        log.info("Actor %s run %s returned %d row(s)", actor_id, run.id, len(rows))
        return rows
