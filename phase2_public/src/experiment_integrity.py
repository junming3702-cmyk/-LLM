"""Experiment B audit/cache transport. No changes to legal decision policy.

Cache only exact requests (including actual evidence), not case IDs. A journal
is private, append-only, single-process, and each provider attempt is recorded.
No reference labels, credentials, or participant scores belong in runtime input.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import time
import uuid

AUDIT_VERSION = "phase2-experiment-b-v1"
ACTIVE_JOURNAL = ContextVar("experiment_journal", default=None)
LABEL_KEYS = {"gold_label", "gold_labels", "gold_legal_basis_chunk_ids",
              "expected_relation", "reference_answer", "reference_verdict",
              "hidden_materials", "hidden_fact_mapping", "expert_label",
              "expert_scores", "hit_gold", "gold_risk_statement",
              "expected_verdict", "expected_conclusion_type", "reference_conclusion",
              "hidden_facts", "deleted_facts", "expert_score", "expert_id",
              "expert_name", "expert_identity", "consensus_label", "consensus_verdict",
              "expected_label", "legal_basis_chunk_ids",
              "legal_basis_locators", "gold_status", "annotator_id", "annotation_state"}
SECRET_KEYS = {"api_key", "apikey", "authorization", "password", "access_token",
               "secret_key", "api_secret"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def file_digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def validate_runtime(value):
    """Reject evaluator fields recursively. Do not use substring matches on prose."""
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in LABEL_KEYS | SECRET_KEYS:
                raise ValueError(f"forbidden_runtime_field:{key}")
            validate_runtime(item)
    elif isinstance(value, list):
        for item in value:
            validate_runtime(item)


def redact(value, secret=""):
    if isinstance(value, dict):
        return {k: "[REDACTED]" if str(k).lower() in SECRET_KEYS else redact(v, secret)
                for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, secret) for v in value]
    if isinstance(value, str) and secret:
        return value.replace(secret, "[REDACTED]")
    return value


def write_new_json(path, value):
    """Exclusive creation: never silently overwrite previous observations."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


def request_fingerprint(url, body, binding):
    # body contains text, context, actual evidence, prompts and model parameters.
    # binding additionally contains corpus/code/method and interaction history.
    return digest({"schema": AUDIT_VERSION, "endpoint": url,
                   "body": body, "binding": binding})


class RunJournal:
    """Persist every request before sending; resume completed HTTP observations.

    Ambiguous/interrupted requests fail closed on resume. Retrying an unknown
    provider outcome requires a new run ID rather than silently invoking again.
    """
    def __init__(self, root, binding, *, resume=False, max_attempts=1):
        if max_attempts not in (1, 2):
            raise ValueError("max_attempts must be 1 or 2")
        self.root = Path(root)
        self.binding = deepcopy(binding)
        self.resume = resume
        self.max_attempts = max_attempts
        self.case_id = None
        self.request_ordinal = 0
        self.current_calls = []
        self.root.mkdir(parents=True, exist_ok=True)
        manifest_path = self.root / "journal_manifest.json"
        manifest = {"schema": AUDIT_VERSION, "binding": binding,
                    "max_attempts": max_attempts}
        if manifest_path.exists():
            old = json.loads(manifest_path.read_text(encoding="utf-8"))
            if old != manifest or not resume:
                raise ValueError("existing journal: use exact-binding resume or a new run ID")
        else:
            write_new_json(manifest_path, manifest)

    @contextmanager
    def case(self, case_id):
        self.case_id = str(case_id)
        self.request_ordinal = 0
        self.current_calls = []
        token = ACTIVE_JOURNAL.set(self)
        try:
            yield self
        finally:
            ACTIVE_JOURNAL.reset(token)

    def event(self, category, value):
        # File is never truncated; historical failures remain in the audit trail.
        path = self.root / "events.jsonl"
        record = {"time": utc_now(), "event": category, "case_id": self.case_id,
                  **deepcopy(value)}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(canonical(record) + "\n")

    def request(self, url, body, api_key, post, *, timeout=180, sleeper=time.sleep):
        self.request_ordinal += 1
        binding = {**self.binding, "case_id": self.case_id,
                   "request_ordinal": self.request_ordinal}
        key = request_fingerprint(url, body, binding)
        cache_path = self.root / "request_cache" / f"{key}.json"
        marker = self.root / "request_cache" / f"{key}.started.json"
        if cache_path.exists():
            if not self.resume:
                raise ValueError("repeated request: use a fresh repeat/run ID")
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("request_key") != key or digest(cached["observation"]) != cached.get("observation_hash"):
                raise ValueError("cache_integrity_failure")
            observation = deepcopy(cached["observation"])
            observation.update(cache_hit=True, incurred_elapsed_seconds=0.0,
                               incurred_usage=None)
            self.current_calls.append(observation)
            self.event("request_cache_hit", {"request_key": key})
            return observation
        if marker.exists():
            raise RuntimeError("interrupted_request_requires_manual_resolution_new_run_id")
        write_new_json(marker, {"request_key": key, "time": utc_now()})
        self.event("request_started", {"request_key": key, "binding": binding,
                                       "request_body": redact(body, api_key)})
        attempts = []
        started = time.monotonic()
        for attempt in range(1, self.max_attempts + 1):
            one = _http_once(url, body, api_key, post, timeout)
            one["attempt"] = attempt
            attempts.append(one)
            self.event("provider_attempt", {"request_key": key, **one})
            retryable = one.get("transport_error") in {"Timeout", "ConnectTimeout", "ReadTimeout", "ConnectionError"} or one.get("http_status") in {429, 502, 503, 504}
            if not retryable or attempt == self.max_attempts:
                break
            self.event("transport_retry", {"request_key": key, "after_attempt": attempt,
                                            "reason": one.get("transport_error") or one.get("http_status")})
            sleeper(1.0)
        observation = {**one, "attempts": attempts, "request_key": key,
                       "elapsed_seconds": round(time.monotonic() - started, 6),
                       "cache_hit": False, "retry_count": len(attempts) - 1,
                       "request_body": redact(body, api_key)}
        observation["incurred_elapsed_seconds"] = observation["elapsed_seconds"]
        observation["incurred_usage"] = [a.get("payload", {}).get("usage") for a in attempts]
        write_new_json(cache_path, {"request_key": key, "observation": observation,
                                    "observation_hash": digest(observation)})
        self.current_calls.append(observation)
        self.event("request_finished", {"request_key": key})
        return observation


def _http_once(url, body, api_key, post, timeout):
    started = time.monotonic()
    try:
        response = post(url, headers={"Authorization": f"Bearer {api_key}",
                                     "Content-Type": "application/json"},
                        json=body, timeout=timeout)
        try:
            payload = response.json()
        except ValueError:
            payload = {"non_json_http_body": response.text}
        if not isinstance(payload, dict):
            payload = {"non_object_http_payload": payload}
        return {"http_status": response.status_code, "ok": response.ok,
                "payload": redact(payload, api_key), "transport_error": None,
                "elapsed_seconds": round(time.monotonic() - started, 6)}
    except Exception as exc:
        # Keep exception type, not credential- or document-bearing error strings.
        return {"http_status": None, "ok": False, "payload": {},
                "transport_error": type(exc).__name__,
                "elapsed_seconds": round(time.monotonic() - started, 6)}


def request_http(url, body, api_key, post, *, timeout=180):
    active = ACTIVE_JOURNAL.get()
    if active is not None:
        return active.request(url, body, api_key, post, timeout=timeout)
    one = _http_once(url, body, api_key, post, timeout)
    return {**one, "request_body": redact(body, api_key), "cache_hit": False,
            "retry_count": 0, "attempts": [one]}


def semantic_verdict(conclusion):
    return {
        "requires_human_legal_confirm": "R", "requires_human_legal_review": "R",
        "potential_risk": "R",
        "no_supported_issue_found_within_review_scope": "N",
        "insufficient_information_needs_human_confirm": "U",
        "insufficient_information": "U",
        "not_supported_by_current_corpus": "U",
        "no_applicable_legal_basis_found_needs_human_confirm": "U",
    }.get(conclusion)


def result_status(result):
    """Do not turn an API/schema failure into a successful legal abstention."""
    gate = result.get("post_llm_gate") or {}
    final = result.get("final_llm_response") or {}
    gate = gate if isinstance(gate, dict) else {"blocked": True}
    final = final if isinstance(final, dict) else {"ok": False}
    response = gate.get("response")
    findings = response.get("findings") or [] if isinstance(response, dict) else []
    failure_level = ((result.get("runtime_input") or {}).get("hierarchy_retrieval_audit") or {}).get("cascade_failure_level")
    if result.get("execution_error") or final.get("ok") is False or failure_level not in (None, "", "none"):
        execution = "execution_failed"
    elif final.get("finish_reason") == "length" or ("parsed" in final and not isinstance(final["parsed"], dict)):
        execution = "invalid_output"
    elif gate.get("blocked") or gate.get("status") == "blocked":
        execution = "gate_blocked"
    elif not isinstance(findings, list) or not findings:
        execution = "invalid_output"
    else:
        execution = "completed"
    mapped = [semantic_verdict(f.get("conclusion_type")) for f in findings if isinstance(f, dict)]
    if execution == "completed" and (len(mapped) != len(findings) or any(v is None for v in mapped)):
        execution = "invalid_output"
    return {"execution_status": execution,
            "verdicts": mapped if execution == "completed" else [],
            "workflow_status": "requires_human_second_review",
            "ready_for_human_delivery": execution == "completed",
            "gate_status": gate.get("status"),
            "gate_reasons": gate.get("actions", [])}


def code_inventory(root):
    root = Path(root)
    paths = sorted([*root.glob("src/*.py"), *root.glob("prompts/*.md")])
    return {str(p.relative_to(root)).replace("\\", "/"): file_digest(p) for p in paths}
