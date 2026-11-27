"""Campus ERP headcount integration — adapter prepared, contract pending.

The campus ERP team has not supplied the API documentation yet, so this
module deliberately implements NO endpoint path, authentication scheme,
request field or response format. What is ready:

- configuration per campus (campus_integrations: base URL, enabled flag,
  timeout, retries) and the credential from the environment only
  (settings.ERP_HEADCOUNT_API_TOKEN; reported as "set"/"not set", never shown);
- an HTTP transport with timeout, bounded retries with back-off on network
  errors and 5xx/429 answers, and errors cleaned of credentials;
- idempotency: each applied ERP record is remembered per campus by its ERP
  key and a hash of its content (erp_headcount_imports), so a repeated or
  overlapping sync never applies a record twice, and a record that changed
  after it was applied is reported for review instead of being re-applied;
- sync runs (erp_sync_runs) with status, counts and a cleaned error, and the
  integration's last-sync timestamp and status.

What waits for the contract (raises ContractPending): the request for a
date range, validating and mapping ERP records into the application's
headcount (meal records), and the rule for ERP figures that differ from a
manually entered headcount. Manual headcount entry is unchanged and remains
the fallback.
"""

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.platform import CampusIntegration, ErpHeadcountImport, ErpSyncRun

KIND = "ERP_HEADCOUNT"
CONTRACT_PENDING = ("The campus ERP headcount API contract has not been supplied yet, so no request "
                    "can be made. Manual headcount entry continues to work.")


class ErpError(Exception):
    """Base class; messages are safe to store and show."""


class NotConfigured(ErpError):
    pass


class ContractPending(ErpError):
    pass


class TransportError(ErpError):
    pass


# ---------- status ----------

def credential_set() -> bool:
    return bool(settings.ERP_HEADCOUNT_API_TOKEN)


def status_of(integration: CampusIntegration | None) -> dict:
    """What the platform shows for one campus. Never includes a secret."""
    base_url = integration.base_url if integration else None
    if not integration or not base_url or not credential_set():
        state, label = "NOT_CONFIGURED", "ERP connection not configured"
    elif not integration.is_enabled:
        state, label = "DISABLED", "Configured, switched off"
    else:
        state, label = "AWAITING_CONTRACT", "Waiting for the ERP API documentation"
    return {
        "kind": KIND, "state": state, "label": label,
        "enabled": bool(integration and integration.is_enabled),
        "base_url": base_url, "credential": "set" if credential_set() else "not set",
        "timeout_seconds": integration.timeout_seconds if integration else 15,
        "max_retries": integration.max_retries if integration else 2,
        "last_sync_at": integration.last_sync_at if integration else None,
        "last_sync_status": integration.last_sync_status if integration else None,
        "last_error": integration.last_error if integration else None,
        "contract": "pending",
    }


# ---------- transport ----------

def redact(message: str) -> str:
    """Removes the credential and anything that looks like one."""
    token = settings.ERP_HEADCOUNT_API_TOKEN
    if token:
        message = message.replace(token, "[redacted]")
    message = re.sub(r"(?i)(authorization|token|api[_-]?key|password|secret)\s*[:=]\s*\S+", r"\1=[redacted]", message)
    message = re.sub(r"//[^/@\s]+@", "//[redacted]@", message)  # user:pass@host
    return message[:500]


@dataclass
class Transport:
    """HTTP with timeout and bounded retries. The authentication header and
    paths are supplied by the contract implementation, not invented here."""
    base_url: str
    timeout_seconds: float
    max_retries: int
    sleep: Callable[[float], None] = time.sleep
    client_factory: Callable[..., httpx.Client] = httpx.Client

    def get_json(self, path: str, *, params: dict | None = None, headers: dict | None = None) -> Any:
        url = self.base_url.rstrip("/") + "/" + path.lstrip("/")
        last = "no attempt made"
        for attempt in range(self.max_retries + 1):
            try:
                with self.client_factory(timeout=self.timeout_seconds) as client:
                    response = client.get(url, params=params, headers=headers or {})
                if response.status_code == 429 or response.status_code >= 500:
                    last = f"ERP answered HTTP {response.status_code}"
                elif response.status_code >= 400:
                    raise TransportError(f"ERP refused the request (HTTP {response.status_code})")
                else:
                    try:
                        return response.json()
                    except ValueError:
                        raise TransportError("ERP answer was not valid JSON") from None
            except httpx.TimeoutException:
                last = f"ERP did not answer within {self.timeout_seconds:g} s"
            except httpx.HTTPError as exc:
                last = redact(f"ERP connection failed: {type(exc).__name__}")
            if attempt < self.max_retries:
                self.sleep(min(2 ** attempt, 8))
        raise TransportError(redact(f"{last} (after {self.max_retries + 1} attempts)"))


# ---------- idempotency ----------

@dataclass(frozen=True)
class HeadcountRecord:
    """A validated ERP record, in application terms. Built only by the
    contract-specific validator (not written yet)."""
    external_key: str
    meal_date: date
    meal_session_id: int
    count: int

    def content_hash(self) -> str:
        body = json.dumps({"d": self.meal_date.isoformat(), "s": self.meal_session_id, "c": self.count}, sort_keys=True)
        return hashlib.sha256(body.encode()).hexdigest()


def plan_imports(db: Session, campus_id: int, records: list[HeadcountRecord]) -> dict[str, list[HeadcountRecord]]:
    """Splits records into new / already applied / changed since applied,
    dropping duplicates within the batch (the first wins)."""
    seen: dict[str, HeadcountRecord] = {}
    duplicates: list[HeadcountRecord] = []
    for record in records:
        if record.external_key in seen:
            duplicates.append(record)
        else:
            seen[record.external_key] = record
    applied = dict(db.query(ErpHeadcountImport.external_key, ErpHeadcountImport.payload_hash)
                   .filter(ErpHeadcountImport.campus_id == campus_id,
                           ErpHeadcountImport.external_key.in_(list(seen) or [""])))
    out: dict[str, list[HeadcountRecord]] = {"new": [], "unchanged": [], "changed": [], "duplicate": duplicates}
    for key, record in seen.items():
        if key not in applied:
            out["new"].append(record)
        elif applied[key] == record.content_hash():
            out["unchanged"].append(record)
        else:
            out["changed"].append(record)
    return out


# ---------- contract-specific parts (pending) ----------

def fetch_headcounts(transport: Transport, date_from: date, date_to: date) -> Any:
    raise ContractPending(CONTRACT_PENDING)


def validate(raw: Any) -> list[HeadcountRecord]:
    raise ContractPending(CONTRACT_PENDING)


def apply_record(db: Session, campus_id: int, record: HeadcountRecord) -> None:
    raise ContractPending(CONTRACT_PENDING)


# ---------- one sync ----------

def sync_campus(db: Session, campus_id: int, triggered_by: int | None, date_from: date, date_to: date) -> ErpSyncRun:
    """Runs one sync and records it. With no contract yet this records a
    NOT_CONFIGURED or CONTRACT_PENDING run and fetches nothing."""
    integration = (db.query(CampusIntegration)
                   .filter(CampusIntegration.campus_id == campus_id, CampusIntegration.kind == KIND).first())
    run = ErpSyncRun(campus_id=campus_id, status="RUNNING", triggered_by=triggered_by)
    db.add(run)
    db.flush()
    status = status_of(integration)
    try:
        if status["state"] == "NOT_CONFIGURED":
            raise NotConfigured("ERP connection not configured (base URL and credential are needed).")
        if status["state"] == "DISABLED":
            raise NotConfigured("The ERP connection is switched off for this campus.")
        transport = Transport(integration.base_url, integration.timeout_seconds, integration.max_retries)
        records = validate(fetch_headcounts(transport, date_from, date_to))
        plan = plan_imports(db, campus_id, records)
        for record in plan["new"]:
            apply_record(db, campus_id, record)
            db.add(ErpHeadcountImport(campus_id=campus_id, external_key=record.external_key,
                                      payload_hash=record.content_hash(), sync_run_id=run.id))
        run.records_received = len(records)
        run.records_applied = len(plan["new"])
        run.records_skipped = len(records) - len(plan["new"])
        run.status = "SUCCEEDED"
    except NotConfigured as exc:
        run.status, run.error = "NOT_CONFIGURED", redact(str(exc))
    except ContractPending as exc:
        run.status, run.error = "CONTRACT_PENDING", redact(str(exc))
    except ErpError as exc:
        run.status, run.error = "FAILED", redact(str(exc))
    run.finished_at = datetime.now(timezone.utc)
    if integration:
        integration.last_sync_at, integration.last_sync_status, integration.last_error = (
            run.finished_at, run.status, run.error)
    return run
