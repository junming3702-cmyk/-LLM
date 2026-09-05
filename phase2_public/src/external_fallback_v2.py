"""Phase 2 external fallback state machine.

The local four-level corpus remains the primary evidence source.  This module
adds an explicit, auditable fallback for discovery and verification without
turning a finite source manifest into an exhaustive search claim.

External responses are untrusted input.  A candidate is never admitted as an
independent legal basis by this module.  It is normalized as a pending,
human-verification candidate and preserves the source's actual normative
level.  CECN candidates are always contextual/supplement-only.

The provider boundary is injectable so the state machine can be tested with
fixtures and can later be connected to an approved search or verification
adapter.  The built-in HTTP provider performs only allowlisted, finite
manifest lookups; a manifest miss therefore remains pending unless a human
attests that the configured manual discovery scope was completed.
"""

from __future__ import annotations

import csv
import hashlib
import html
import ipaddress
import json
import re
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol
from urllib.parse import urlparse

import requests


SCHEMA_VERSION = "stage3_external_fallback_v2"

NOT_CALLED = "not_called"
PENDING_PROVIDER = "pending_provider"
PENDING_HUMAN_SCOPE = "pending_human_scope_attestation"
RUNNING = "running"
COMPLETED_WITH_CANDIDATES = "completed_with_candidates"
COMPLETED_NO_HIT = "completed_no_hit"
FAILED = "failed"

COMPLETED_STATUSES = {COMPLETED_WITH_CANDIDATES, COMPLETED_NO_HIT}
TERMINAL_STATUSES = COMPLETED_STATUSES | {FAILED, NOT_CALLED}

# The exported aggregate uses five states.  Mode-level records retain the
# precise pending reason so a caller can distinguish an absent provider from
# a missing manual-scope attestation.
FIVE_STATE_EXPORTS = {NOT_CALLED, "pending", FAILED, COMPLETED_NO_HIT, "hit"}

DISCOVERY_REASON = "no_usable_applicable_local_level_1_to_4_basis"

# Keep this policy in one importable pure predicate.  The post-LLM gate may
# import ``is_usable_legal_basis`` so Stage 3 fallback eligibility and final
# evidence admission cannot drift apart.  Missing optional fields remain
# compatible with the frozen local corpus; explicit negative/null values do
# not receive that compatibility treatment.
_REJECTED_LEGAL_EVIDENCE_ELIGIBILITY = frozenset({
    "supplement_only",
    "verification_only",
    "not_admitted",
})
_REJECTED_RETRIEVAL_ADMISSIONS = frozenset({
    "supplement_candidate_pool",
    "excluded_pending_review",
    "control_only",
    "range_only",
    "blocked",
    "not_admitted",
})
_UNVERIFIED_STATUSES = frozenset({
    "pending_human_verification",
    "pending",
    "unverified",
    "not_admitted",
})
_INAPPLICABLE_STATUSES = frozenset({"mismatch", "not_applicable"})

_ARTICLE_PATTERN = re.compile(
    r"(?:第\s*[0-9一二三四五六七八九十百千万]+\s*条|Article\s+[0-9]+)",
    re.IGNORECASE,
)
_PLACEHOLDER_PATTERN = re.compile(
    r"(?:exact article|candidate only|待核验|待确认|placeholder|未确认|unknown article)",
    re.IGNORECASE,
)
_PRIVATE_QUERY_PATTERN = re.compile(
    r"(?:[A-Za-z]:[\\/]|\\\\|/(?:Users|home|private|var)/|\b(?:password|passwd|token|secret|api[_ -]?key)\b|\S+@\S+|\b1[3-9]\d{9}\b)",
    re.IGNORECASE,
)
_SENSITIVE_URL_QUERY_PATTERN = re.compile(
    r"(?:password|passwd|token|secret|api[_-]?key|access[_-]?token|authorization)",
    re.IGNORECASE,
)


def _normalise_public_page_text(value: Any) -> str:
    """Make a fetched public page comparable to manifest-provided targets.

    This is deliberately a small deterministic check, not a general HTML
    parser or a web-search implementation.  The manifest supplies the exact
    title/article/quote target; the page only has to contain that target after
    harmless tag/entity/whitespace normalisation.
    """

    text = html.unescape(_text(value))
    text = re.sub(r"<[^>]{0,500}>", " ", text)
    return re.sub(r"\s+", "", text).lower()


def _manifest_article_target(entry: Mapping[str, Any]) -> dict[str, str]:
    """Read an optional, explicit article target from one manifest row."""

    return {
        "law_title": _text(
            entry.get("law_title")
            or entry.get("expected_law_title")
            or entry.get("title")
        ),
        "article": _text(entry.get("article") or entry.get("expected_article")),
        "expected_quote": _text(
            entry.get("expected_quote")
            or entry.get("expected_legal_quote")
            or entry.get("legal_quote")
        ),
        "issuer": _text(entry.get("issuer") or entry.get("issuing_authority")),
        "version": _text(entry.get("version") or entry.get("version_label")),
        "effective_date": _text(entry.get("effective_date") or entry.get("effective")),
        "normative_level": _text(entry.get("normative_level") or entry.get("actual_normative_level")),
        "source_locator": _text(entry.get("source_locator") or entry.get("article_locator")),
        "publishing_site": _text(entry.get("publishing_site")),
        "provenance_reference_url": _text(entry.get("provenance_reference_url")),
        "source_status": _text(entry.get("source_status")),
    }


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json_safe(value: Any) -> Any:
    """Return a JSON-serializable copy for provider/audit boundaries."""

    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def load_external_manifest(path: Path) -> list[dict[str, str]]:
    """Load the separate external-source CSV manifest.

    The CSV is configuration, not evidence.  It cannot mark an external
    search complete by itself.
    """

    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {str(key).strip(): _text(value) for key, value in row.items()}
            for row in csv.DictReader(handle)
            if any(_text(value) for value in row.values())
        ]


def _hostname_is_public(hostname: str) -> bool:
    host = hostname.rstrip(".").lower()
    if not host or host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )


def _resolve_addresses_are_public(hostname: str, port: int) -> bool:
    """Reject DNS answers that resolve a public-looking URL to a private host."""

    try:
        addresses = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except OSError:
        # A provider may be offline.  The state machine will report a network
        # failure; do not treat an unresolved hostname as proof of safety.
        return False
    if not addresses:
        return False
    for address_info in addresses:
        address = address_info[4][0]
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            return False
        if (
            parsed.is_private
            or parsed.is_loopback
            or parsed.is_link_local
            or parsed.is_reserved
            or parsed.is_multicast
            or parsed.is_unspecified
        ):
            return False
    return True


def validate_public_allowlisted_url(url: str, manifest_entries: Iterable[Mapping[str, Any]]) -> tuple[bool, str]:
    """Validate an external URL against explicit manifest hosts/paths.

    Redirects are checked by the HTTP provider as well.  Userinfo and secret
    query parameters are rejected so a URL cannot exfiltrate credentials.
    """

    parsed = urlparse(_text(url))
    if parsed.scheme not in {"http", "https"}:
        return False, "unsupported_url_scheme"
    if parsed.username or parsed.password:
        return False, "url_userinfo_not_allowed"
    if not _hostname_is_public(parsed.hostname or ""):
        return False, "private_or_local_hostname_blocked"
    if _SENSITIVE_URL_QUERY_PATTERN.search(parsed.query or ""):
        return False, "sensitive_url_query_blocked"

    candidates: list[tuple[str, str]] = []
    for entry in manifest_entries:
        base = urlparse(_text(entry.get("base_url")))
        if base.scheme in {"http", "https"} and base.hostname:
            candidates.append((base.hostname.lower().rstrip("."), base.path.rstrip("/") or "/"))
    if not candidates:
        return False, "no_manifest_allowlist_entry"
    host = (parsed.hostname or "").lower().rstrip(".")
    path = parsed.path.rstrip("/") or "/"
    allowed = any(
        host == allowed_host and (path == allowed_path or path.startswith(allowed_path.rstrip("/") + "/"))
        for allowed_host, allowed_path in candidates
    )
    if not allowed:
        return False, "url_not_in_manifest_allowlist"
    return True, "allowlisted_public_url"


def sanitize_legal_query_terms(values: Iterable[Any]) -> tuple[list[str], list[str]]:
    """Accept legal-only query terms and reject likely private document text."""

    accepted: list[str] = []
    rejected: list[str] = []
    for raw in values:
        value = _text(raw)
        if not value:
            continue
        if len(value) > 200 or _PRIVATE_QUERY_PATTERN.search(value):
            rejected.append("query_rejected_private_or_sensitive_pattern")
            continue
        accepted.append(value)
    # Do not include the rejected text in logs or provider requests.
    return list(dict.fromkeys(accepted)), rejected


@dataclass(frozen=True)
class ExternalRequest:
    mode: str
    issue_id: str
    local_search_completion: dict[str, Any]
    verification_reasons: tuple[str, ...]
    legal_query_terms: tuple[str, ...]
    query_ids: tuple[str, ...]
    manifest_entries: tuple[dict[str, Any], ...]
    project_scope: dict[str, Any]


@dataclass
class ProviderResponse:
    provider_id: str
    status: str = "pending"
    candidates: list[dict[str, Any]] = field(default_factory=list)
    executed_search_scope: list[str] = field(default_factory=list)
    configured_search_scope: list[str] = field(default_factory=list)
    scope_completed: bool = False
    scope_completion_basis: str = "none"
    human_attested: bool = False
    query_ids: list[str] = field(default_factory=list)
    failure_reason: str = ""
    provider_mode: str = ""
    fetch_records: list[dict[str, Any]] = field(default_factory=list)
    provider_call_attempted: bool = True
    http_called: bool = False
    http_call_count: int = 0
    scope_attestation_id: str = ""


class ExternalProvider(Protocol):
    provider_id: str

    def execute(self, request: ExternalRequest) -> ProviderResponse:
        ...


def _entry_id(entry: Mapping[str, Any]) -> str:
    return _text(entry.get("external_source_id") or entry.get("source_id") or entry.get("source_name"))


def _is_cecn(entry: Mapping[str, Any], candidate: Mapping[str, Any] | None = None) -> bool:
    values = [
        _text(entry.get("external_source_id")),
        _text(entry.get("source_name")),
        _text(entry.get("source_category")),
        _text(candidate.get("provider_id")) if candidate else "",
        _text(candidate.get("source_category")) if candidate else "",
    ]
    joined = " ".join(values).lower()
    return "cecn" in joined or "建设造价信息网" in joined or "industry_cost_information" in joined


def _manifest_entry_for_url(url: str, entries: Iterable[Mapping[str, Any]]) -> dict[str, Any] | None:
    parsed = urlparse(_text(url))
    host = (parsed.hostname or "").lower().rstrip(".")
    path = parsed.path.rstrip("/") or "/"
    for entry in entries:
        base = urlparse(_text(entry.get("base_url")))
        base_host = (base.hostname or "").lower().rstrip(".")
        base_path = base.path.rstrip("/") or "/"
        if host == base_host and (path == base_path or path.startswith(base_path.rstrip("/") + "/")):
            return dict(entry)
    return None


def normalize_external_candidate(
    raw: Mapping[str, Any],
    *,
    request: ExternalRequest,
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate and normalize one provider candidate.

    A valid candidate remains pending human confirmation and non-independent.
    """

    if not isinstance(raw, Mapping):
        return None, "candidate_not_object"
    source_url = _text(raw.get("source_url") or raw.get("official_source_url") or raw.get("url"))
    allowed, url_reason = validate_public_allowlisted_url(source_url, request.manifest_entries)
    if not allowed:
        return None, f"candidate_url_rejected:{url_reason}"
    entry = _manifest_entry_for_url(source_url, request.manifest_entries) or {}

    article = _text(raw.get("article") or raw.get("article_reference"))
    legal_quote = _text(raw.get("legal_quote") or raw.get("article_text") or raw.get("text"))
    required = {
        "article": article,
        "legal_quote": legal_quote,
        # ``authority_role`` is a use-policy label, not an issuing authority.
        # It must never be promoted to provenance when the provider omitted
        # the actual issuer.
        "issuer": _text(
            raw.get("issuer")
            or raw.get("issuing_authority")
            or entry.get("issuer")
            or entry.get("issuing_authority")
        ),
        "title": _text(raw.get("title") or raw.get("source_title") or entry.get("source_name")),
        "version": _text(
            raw.get("version")
            or raw.get("version_label")
            or entry.get("version")
            or entry.get("version_label")
        ),
        "effective_date": _text(
            raw.get("effective_date")
            or raw.get("effective")
            or entry.get("effective_date")
            or entry.get("effective")
        ),
        "retrieved_at": _text(raw.get("retrieved_at") or raw.get("retrieved_time")) or now_utc(),
        "content_sha256": _text(raw.get("content_sha256") or raw.get("hash")),
        "normative_level": _text(raw.get("normative_level") or raw.get("actual_normative_level")),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        return None, "candidate_missing_required_fields:" + ",".join(missing)
    if not _ARTICLE_PATTERN.search(article) or _PLACEHOLDER_PATTERN.search(article):
        return None, "candidate_article_is_not_specific_full_article_reference"
    if _PLACEHOLDER_PATTERN.search(legal_quote) or len(legal_quote) < 4:
        return None, "candidate_legal_quote_is_placeholder_or_empty"
    if required["content_sha256"].lower() != sha256_text(legal_quote).lower():
        return None, "candidate_hash_does_not_match_legal_quote"

    cecn_only = _is_cecn(entry, raw)
    candidate_id = _text(raw.get("candidate_id") or raw.get("external_source_id"))
    if not candidate_id:
        candidate_id = f"EXT-{sha256_text(source_url + article)[:12]}"
    source_category = _text(raw.get("source_category") or entry.get("source_category")) or "external_source"
    source_locator = _text(raw.get("source_locator") or raw.get("article_locator"))
    if not source_locator:
        source_locator = f"{source_url}#article={article}"
    # These aliases are intentional: the gate's runtime-owned evidence
    # contract uses source_title/source_version/source_hash, while the
    # provider boundary also preserves title/version/content_sha256 for
    # backwards-compatible audit consumers.
    source_title = required["title"]
    source_version = required["version"]
    source_hash = required["content_sha256"]
    record = {
        "candidate_id": candidate_id,
        "chunk_id": _text(raw.get("chunk_id")) or f"external:{candidate_id}",
        "external_candidate": True,
        "external_source": True,
        "source_url": source_url,
        "official_source_url": source_url,
        "external_source_url": source_url,
        "external_source_id": _entry_id(entry) or _text(raw.get("external_source_id")),
        "provider_id": request.mode + ":" + _text(raw.get("provider_id")) if raw.get("provider_id") else "",
        "issuer": required["issuer"],
        "title": source_title,
        "source_title": source_title,
        "law": source_title,
        "version": source_version,
        "source_version": source_version,
        "effective_date": required["effective_date"],
        "retrieved_at": required["retrieved_at"],
        "content_sha256": source_hash,
        "source_hash": source_hash,
        "publishing_site": _text(raw.get("publishing_site") or entry.get("publishing_site")),
        "provenance_reference_url": _text(
            raw.get("provenance_reference_url") or entry.get("provenance_reference_url")
        ),
        "source_status": _text(raw.get("source_status") or entry.get("source_status"))
        or "provider_asserted_pending_current_version_verification",
        "article": article,
        "legal_quote": legal_quote,
        "source_locator": source_locator,
        # This is deliberately copied from the provider/manifest.  No source
        # acquisition channel is allowed to coerce it to Level 4.
        "normative_level": required["normative_level"],
        "actual_normative_level": required["normative_level"],
        "normative_type": _text(raw.get("normative_type") or entry.get("source_category")) or "external_source",
        "source_role": "external_candidate",
        "external_evidence_role": "external_candidate",
        "source_category": source_category,
        "provenance_origin": "external",
        "acquisition_channel": "external_retrieval",
        "retrieval_stage": f"external_fallback_{request.mode}",
        "human_confirmation_status": "pending",
        "provider_claimed_human_confirmation_status": _text(raw.get("human_confirmation_status")),
        "human_confirmation_required": True,
        "independent_legal_evidence": False,
        "legal_evidence_eligibility": "supplement_only" if cecn_only else "verification_only",
        "citation_mode": "contextual_only" if cecn_only else "verification_only",
        "citation_ready": False,
        "requires_human_review": True,
        "cecn_candidate_only": cecn_only,
        "external_candidate_status": "pending_human_source_confirmation",
        "normative_level_status": "provider_asserted_pending_human_validation",
        "verification_status": "pending_human_verification",
        "retrieval_admission": "supplement_candidate_pool" if cecn_only else "excluded_pending_review",
        "reference_purpose": "external_verification_candidate" if not cecn_only else "out_of_scope_context_only",
        "scope_classification": _text(raw.get("scope_classification")) or "unknown_external_scope",
        "geographic_scope": _text(raw.get("geographic_scope")) or "unknown_until_human_verification",
        "project_type_scope": _text(raw.get("project_type_scope")) or "unknown_until_human_verification",
        "applicability_status": "pending_human_applicability_confirmation",
        "applicability_basis": "external candidate requires manual source and scope verification",
        "evidence_support_confidence": "low",
        "applicability_confidence": "low",
        "external_provenance": {
            "provider_id": _text(raw.get("provider_id")),
            "manifest_source_id": _entry_id(entry),
            "official_url_allowlist_checked": True,
            "source_locator": source_locator,
            "source_title": source_title,
            "source_version": source_version,
            "source_hash": source_hash,
            "publishing_site": _text(raw.get("publishing_site") or entry.get("publishing_site")),
            "provenance_reference_url": _text(
                raw.get("provenance_reference_url") or entry.get("provenance_reference_url")
            ),
            "source_status": _text(raw.get("source_status") or entry.get("source_status"))
            or "provider_asserted_pending_current_version_verification",
            "source_acquisition_does_not_change_normative_level": True,
            "human_verification_record_id": "",
        },
    }
    return record, None


class ManifestHttpProvider:
    """Finite, allowlisted HTTP fetcher for the current source manifest.

    It does not implement open-web search.  It fetches each configured URL and
    records transport metadata.  When a manifest row explicitly supplies a
    law title, article and expected full quote (plus provenance fields), the
    provider performs a deterministic containment check against the fetched
    page and emits a pending human-verification candidate.  Rows without that
    complete target remain lookup-only.  A finite manifest fetch or match is
    never an exhaustive discovery claim.
    """

    provider_id = "manifest_http_v2"

    def __init__(self, manifest_entries: Iterable[Mapping[str, Any]], timeout_seconds: float = 20.0) -> None:
        self.manifest_entries = [dict(entry) for entry in manifest_entries]
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _target_candidate(
        entry: Mapping[str, Any],
        *,
        source_url: str,
        page_content: Any,
        retrieved_at: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """Match one explicit manifest article target without web search."""

        target = _manifest_article_target(entry)
        required_target_fields = (
            "law_title",
            "article",
            "expected_quote",
            "issuer",
            "version",
            "effective_date",
            "normative_level",
        )
        missing = [field for field in required_target_fields if not target.get(field)]
        match_record: dict[str, Any] = {
            "target_declared": bool(any(target.values())),
            "target_complete": not missing,
            "target_missing_fields": missing,
            "article_match": False,
            "quote_match": False,
            "title_match": False,
            "expected_quote_sha256": sha256_text(target["expected_quote"])
            if target.get("expected_quote")
            else "",
        }
        if missing:
            match_record["status"] = "lookup_only_missing_article_target_fields"
            return None, match_record

        page = _normalise_public_page_text(page_content)
        article = _normalise_public_page_text(target["article"])
        quote = _normalise_public_page_text(target["expected_quote"])
        title = _normalise_public_page_text(target["law_title"])
        match_record["article_match"] = bool(article and article in page)
        match_record["quote_match"] = bool(quote and quote in page)
        match_record["title_match"] = bool(title and title in page)
        if not (
            match_record["article_match"]
            and match_record["quote_match"]
            and match_record["title_match"]
        ):
            match_record["status"] = "declared_article_target_not_found_in_fetched_page"
            return None, match_record

        match_record["status"] = "declared_article_target_matched_pending_human_confirmation"
        candidate_id = _text(entry.get("candidate_id")) or (
            f"EXT-{sha256_text(source_url + target['article'])[:12]}"
        )
        candidate = {
            "candidate_id": candidate_id,
            "source_url": source_url,
            "official_source_url": source_url,
            "source_locator": target["source_locator"] or f"{source_url}#article={target['article']}",
            "issuer": target["issuer"],
            "title": target["law_title"],
            "source_title": target["law_title"],
            "version": target["version"],
            "source_version": target["version"],
            "effective_date": target["effective_date"],
            "retrieved_at": retrieved_at,
            "content_sha256": sha256_text(target["expected_quote"]),
            "source_hash": sha256_text(target["expected_quote"]),
            "article": target["article"],
            "legal_quote": target["expected_quote"],
            "normative_level": target["normative_level"],
            "actual_normative_level": target["normative_level"],
            "source_category": _text(entry.get("source_category")) or "external_source",
            "publishing_site": target["publishing_site"],
            "provenance_reference_url": target["provenance_reference_url"],
            "source_status": target["source_status"] or "provider_asserted_pending_current_version_verification",
            "provider_id": ManifestHttpProvider.provider_id,
        }
        return candidate, match_record

    def execute(self, request: ExternalRequest) -> ProviderResponse:
        configured = [
            _entry_id(entry)
            for entry in self.manifest_entries
            if _entry_id(entry)
        ]
        records: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []
        executed: list[str] = []
        http_call_count = 0
        for entry in self.manifest_entries:
            source_id = _entry_id(entry)
            url = _text(entry.get("base_url"))
            if not source_id or not url:
                continue
            allowed, reason = validate_public_allowlisted_url(url, self.manifest_entries)
            if not allowed:
                records.append({"source_id": source_id, "url": url, "status": "blocked", "reason": reason})
                continue
            parsed = urlparse(url)
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            if not _resolve_addresses_are_public(parsed.hostname or "", port):
                records.append({"source_id": source_id, "url": url, "status": "failed", "reason": "dns_resolution_not_public_or_unavailable"})
                continue
            started = time.monotonic()
            try:
                http_call_count += 1
                response = requests.get(
                    url,
                    headers={"User-Agent": "phase2-external-verification/2.0"},
                    timeout=self.timeout_seconds,
                    allow_redirects=False,
                )
                elapsed = round(time.monotonic() - started, 3)
                record: dict[str, Any] = {
                    "source_id": source_id,
                    "url": url,
                    "http_status": response.status_code,
                    "elapsed_seconds": elapsed,
                    "response_sha256": hashlib.sha256(response.content).hexdigest(),
                    "content_type": response.headers.get("content-type", ""),
                    "status": "fetched" if response.ok else "http_error",
                }
                if response.ok:
                    retrieved_at = now_utc()
                    page_content = getattr(response, "content", b"")
                    if isinstance(page_content, bytes):
                        page_content = page_content.decode("utf-8", errors="replace")
                    candidate, target_record = self._target_candidate(
                        entry,
                        source_url=url,
                        page_content=page_content,
                        retrieved_at=retrieved_at,
                    )
                    record["article_target_check"] = target_record
                    if candidate is not None:
                        candidates.append(candidate)
                        record["candidate_id"] = candidate["candidate_id"]
                        record["candidate_status"] = "pending_human_source_confirmation"
                        record["candidate_locator"] = candidate["source_locator"]
                records.append(record)
                if response.ok:
                    executed.append(source_id)
            except requests.RequestException as exc:
                records.append({"source_id": source_id, "url": url, "status": "failed", "reason": type(exc).__name__})

        successful_fetches = [record for record in records if record.get("status") == "fetched"]
        failed_fetches = [record for record in records if record.get("status") in {"failed", "http_error"}]
        if candidates:
            status = "completed"
            failure_reason = ""
        elif successful_fetches:
            # A finite manifest fetch is useful transport evidence but is not
            # an exhaustive legal search and supplies no article candidate.
            status = "pending"
            failure_reason = "manifest_lookup_returned_no_normalized_article_candidate"
        elif failed_fetches:
            status = "failed"
            failure_reason = "all_manifest_fetches_failed_or_returned_http_error"
        else:
            status = "pending"
            failure_reason = "manifest_scope_not_exhaustive_and_no_successful_fetch"
        return ProviderResponse(
            provider_id=self.provider_id,
            status=status,
            candidates=candidates,
            executed_search_scope=executed,
            configured_search_scope=configured,
            scope_completed=False,
            scope_completion_basis="manifest_lookup",
            human_attested=False,
            query_ids=list(request.query_ids),
            failure_reason=failure_reason,
            provider_mode="manifest_lookup_only",
            fetch_records=records,
            provider_call_attempted=True,
            http_called=http_call_count > 0,
            http_call_count=http_call_count,
        )


class ExternalFallbackStateMachine:
    """Run discovery/verification fallbacks with explicit completion semantics."""

    def __init__(
        self,
        *,
        enabled: bool,
        provider: ExternalProvider | None,
        manifest_entries: Iterable[Mapping[str, Any]] = (),
    ) -> None:
        self.enabled = bool(enabled)
        self.provider = provider
        self.manifest_entries = tuple(dict(entry) for entry in manifest_entries)

    def _base_record(self, mode: str, *, requested: bool, reason: str = "") -> dict[str, Any]:
        return {
            "mode": mode,
            "status": NOT_CALLED if not requested else PENDING_PROVIDER,
            "requested": requested,
            "dispatch_attempted": False,
            "provider_call_attempted": False,
            "provider_method_invoked": False,
            "provider_reported_call_attempted": False,
            "http_called": False,
            "http_call_count": 0,
            "provider_response_status": "not_called",
            "transport_status": "not_called",
            "executed": False,
            "provider_id": _text(getattr(self.provider, "provider_id", "")),
            "provider_mode": "",
            "configured_search_scope": [_entry_id(entry) for entry in self.manifest_entries if _entry_id(entry)],
            "executed_search_scope": [],
            "scope_completion_basis": "none",
            "scope_completion_attested": False,
            "scope_attestation_id": "",
            "scope_coverage_ok": False,
            "scope_completion_evidence": {},
            "human_attested": False,
            "external_search_completed": False,
            "candidate_count": 0,
            "raw_candidate_count": 0,
            "rejected_candidate_count": 0,
            "candidate_ids": [],
            "candidates": [],
            "partial_candidates": [],
            "partial_candidate_ids": [],
            "partial_candidate_count": 0,
            "query_ids": [],
            "failure_reason": reason,
            "trigger_reason": "",
            "started_at": "",
            "completed_at": "",
            "fetch_records": [],
            "normalization_rejections": [],
        }

    @staticmethod
    def _export_mode_status(record: dict[str, Any]) -> dict[str, Any]:
        raw_status = record.get("status")
        if raw_status in {PENDING_PROVIDER, PENDING_HUMAN_SCOPE, RUNNING}:
            export_status = "pending"
        elif raw_status == COMPLETED_WITH_CANDIDATES:
            export_status = "hit"
        else:
            export_status = raw_status
        record["export_status"] = export_status
        return record

    def _execute(
        self,
        mode: str,
        *,
        issue_id: str,
        local_search_completion: dict[str, Any],
        verification_reasons: list[str],
        legal_query_terms: list[str],
        query_ids: list[str],
        project_scope: dict[str, Any],
        trigger_reason: str,
    ) -> dict[str, Any]:
        record = self._base_record(mode, requested=True)
        record.update({
            "status": RUNNING,
            "executed": True,
            "dispatch_attempted": True,
            "trigger_reason": trigger_reason,
            "started_at": now_utc(),
        })
        accepted_terms, rejected_terms = sanitize_legal_query_terms(legal_query_terms)
        if rejected_terms:
            record["normalization_rejections"].extend(rejected_terms)
        request = ExternalRequest(
            mode=mode,
            issue_id=_text(issue_id),
            local_search_completion=_json_safe(local_search_completion),
            verification_reasons=tuple(dict.fromkeys(_text(value) for value in verification_reasons if _text(value))),
            legal_query_terms=tuple(accepted_terms),
            query_ids=tuple(dict.fromkeys(_text(value) for value in query_ids if _text(value))),
            manifest_entries=tuple(_json_safe(entry) for entry in self.manifest_entries),
            project_scope=_json_safe(project_scope),
        )
        record["query_ids"] = list(request.query_ids)
        if self.provider is None:
            record.update(
                {
                    "status": PENDING_PROVIDER,
                    "executed": False,
                    "provider_call_attempted": False,
                    "failure_reason": "no_external_provider_configured",
                    "completed_at": now_utc(),
                }
            )
            return self._export_mode_status(record)
        try:
            provider_response = self.provider.execute(request)
        except Exception as exc:  # provider failures are data, never successful no-hit
            record.update(
                {
                    "status": FAILED,
                    "provider_call_attempted": True,
                    "provider_method_invoked": True,
                    "failure_reason": f"provider_exception:{type(exc).__name__}",
                    "completed_at": now_utc(),
                }
            )
            return self._export_mode_status(record)
        if not isinstance(provider_response, ProviderResponse):
            record.update(
                {
                    "status": FAILED,
                    "provider_call_attempted": True,
                    "provider_method_invoked": True,
                    "failure_reason": "provider_returned_invalid_response_object",
                    "completed_at": now_utc(),
                }
            )
            return self._export_mode_status(record)
        record.update(
            {
                "provider_id": provider_response.provider_id,
                # Reaching this branch proves that the provider method was
                # invoked.  Keep the provider's own flag separately so a
                # stale response cannot make an invoked call look like
                # not_called.
                "provider_call_attempted": True,
                "provider_method_invoked": True,
                "provider_reported_call_attempted": bool(provider_response.provider_call_attempted),
                "http_called": bool(provider_response.http_called),
                "http_call_count": int(provider_response.http_call_count or 0),
                "provider_mode": provider_response.provider_mode,
                "configured_search_scope": list(provider_response.configured_search_scope),
                "executed_search_scope": list(provider_response.executed_search_scope),
                "scope_completion_basis": provider_response.scope_completion_basis,
                "scope_completion_attested": bool(provider_response.human_attested)
                or provider_response.scope_completion_basis == "human_attested_manual_discovery",
                "scope_attestation_id": _text(provider_response.scope_attestation_id),
                "human_attested": bool(provider_response.human_attested),
                "query_ids": list(dict.fromkeys(provider_response.query_ids or list(request.query_ids))),
                "raw_candidate_count": len(provider_response.candidates),
                "fetch_records": _json_safe(provider_response.fetch_records),
                "failure_reason": provider_response.failure_reason,
                "completed_at": now_utc(),
            }
        )
        provider_status = _text(provider_response.status).lower()
        record["provider_response_status"] = provider_status or "unknown"
        record["transport_status"] = "failed" if provider_status in {"failed", "error", "transport_failed", "network_failure"} else "response_received"
        configured_scope = {
            _text(value)
            for value in (provider_response.configured_search_scope or list(request.query_ids))
            if _text(value)
        }
        executed_scope = {
            _text(value)
            for value in provider_response.executed_search_scope
            if _text(value)
        }
        scope_coverage_ok = bool(executed_scope) and configured_scope.issubset(executed_scope)
        if provider_response.scope_completion_basis == "provider_execution":
            scope_complete = bool(provider_response.scope_completed) and scope_coverage_ok
        elif provider_response.scope_completion_basis == "human_attested_manual_discovery":
            scope_complete = bool(
                provider_response.scope_completed
                and provider_response.human_attested
                and _text(provider_response.scope_attestation_id)
                and scope_coverage_ok
            )
        else:
            scope_complete = False
        record["scope_coverage_ok"] = scope_coverage_ok
        record["scope_completion_evidence"] = {
            "configured_search_scope": sorted(configured_scope),
            "executed_search_scope": sorted(executed_scope),
            "coverage_ok": scope_coverage_ok,
            "scope_completed_claim": bool(provider_response.scope_completed),
            "completion_basis": provider_response.scope_completion_basis,
            "human_attested": bool(provider_response.human_attested),
            "scope_attestation_id_present": bool(_text(provider_response.scope_attestation_id)),
        }
        record["external_search_completed"] = scope_complete
        if provider_response.scope_completed and not scope_complete:
            record["failure_reason"] = (
                "provider_scope_completion_claim_rejected; actual executed scope or human attestation is incomplete"
            )

        normalized: list[dict[str, Any]] = []
        rejections: list[str] = []
        for raw_candidate in provider_response.candidates:
            candidate, rejection = normalize_external_candidate(raw_candidate, request=request)
            if candidate is None:
                rejections.append(rejection or "candidate_rejected")
            else:
                candidate["provider_id"] = provider_response.provider_id
                candidate["external_provenance"]["provider_id"] = provider_response.provider_id
                normalized.append(candidate)
        record["normalization_rejections"] = rejections
        record["rejected_candidate_count"] = len(rejections)

        # A transport/provider failure is decisive even when an adapter
        # returns partial material alongside the failure.  Keep that material
        # in a separate audit field so it cannot be mistaken for a successful
        # hit or for an exhausted no-hit search.
        provider_failed = provider_status in {"failed", "error", "transport_failed", "network_failure"}
        if provider_failed:
            record["partial_candidates"] = normalized
            record["partial_candidate_ids"] = [candidate["candidate_id"] for candidate in normalized]
            record["partial_candidate_count"] = len(normalized)
            record["candidates"] = []
            record["candidate_ids"] = []
            record["candidate_count"] = 0
            record["status"] = FAILED
            record["external_search_completed"] = False
            if not record["failure_reason"]:
                record["failure_reason"] = "provider_reported_transport_or_search_failure"
            return self._export_mode_status(record)

        # A provider explicitly reporting not_called has not performed a
        # search, regardless of any stale scope flags or payload material.
        # Preserve any such material as partial only and never convert it to
        # completed_no_hit.
        if provider_status == "not_called":
            record["partial_candidates"] = normalized
            record["partial_candidate_ids"] = [candidate["candidate_id"] for candidate in normalized]
            record["partial_candidate_count"] = len(normalized)
            record["candidates"] = []
            record["candidate_ids"] = []
            record["candidate_count"] = 0
            record["status"] = PENDING_PROVIDER
            record["external_search_completed"] = False
            record["failure_reason"] = record["failure_reason"] or "provider_reported_not_called"
            return self._export_mode_status(record)

        record["candidates"] = normalized
        record["candidate_ids"] = [candidate["candidate_id"] for candidate in normalized]
        record["candidate_count"] = len(normalized)
        if normalized:
            record["status"] = COMPLETED_WITH_CANDIDATES
            if rejections:
                record["failure_reason"] = "some_provider_candidates_rejected; human_source_confirmation_required"
            return self._export_mode_status(record)
        if provider_response.candidates:
            # A provider returned material, but every candidate failed the
            # provenance/article/hash checks.  This is not a no-result search
            # and must not satisfy the no-applicable-law branch.
            record["status"] = PENDING_HUMAN_SCOPE
            record["external_search_completed"] = False
            record["failure_reason"] = "all_provider_candidates_rejected_by_provenance_gate"
            return self._export_mode_status(record)
        if provider_status == "pending":
            record["status"] = PENDING_HUMAN_SCOPE
            record["external_search_completed"] = False
            record["failure_reason"] = record["failure_reason"] or "provider_scope_pending_or_not_exhaustive"
            return self._export_mode_status(record)
        if provider_status in {"completed", "success", "no_hit", "nohit"} and scope_complete:
            record["status"] = COMPLETED_NO_HIT
        else:
            record["status"] = PENDING_HUMAN_SCOPE
            record["external_search_completed"] = False
            if not record["failure_reason"]:
                record["failure_reason"] = (
                    "search_scope_completion_not_attested"
                    if provider_status in {"completed", "success", "no_hit", "nohit"}
                    else "provider_status_not_accepted_as_completed_search"
                )
        return self._export_mode_status(record)

    def run(
        self,
        *,
        issue_id: str,
        local_search_completion: Mapping[str, Any],
        verification_reasons: Iterable[Any] = (),
        legal_query_terms: Iterable[Any] = (),
        query_ids: Iterable[Any] = (),
        project_scope: Mapping[str, Any] | None = None,
        local_explicit_satisfaction: bool = False,
    ) -> dict[str, Any]:
        local = _json_safe(dict(local_search_completion))
        reasons = list(dict.fromkeys(_text(value) for value in verification_reasons if _text(value)))
        safe_terms, rejected_terms = sanitize_legal_query_terms(legal_query_terms)
        ids = list(dict.fromkeys(_text(value) for value in query_ids if _text(value)))
        scope = _json_safe(dict(project_scope or {}))
        local_no_basis = bool(local.get("no_usable_applicable_basis"))
        local_complete_no_hit = local.get("status") == COMPLETED_NO_HIT and local_no_basis
        local_discovery_eligible = bool(local.get("fallback_discovery_eligible", local_complete_no_hit))
        local_no_applicable_eligible = bool(local.get("no_applicable_status_eligible", local_complete_no_hit))
        discovery_requested = local_discovery_eligible and not local_explicit_satisfaction
        verification_requested = bool(reasons)

        discovery = self._base_record(
            "discovery",
            requested=discovery_requested,
            reason="" if discovery_requested else (
                "external_fallback_disabled"
                if not self.enabled
                else "local_explicit_satisfaction_or_usable_basis_present"
            ),
        )
        verification = self._base_record(
            "verification",
            requested=verification_requested,
            reason="" if verification_requested else (
                "external_fallback_disabled"
                if not self.enabled
                else "no_version_status_or_applicability_doubt_recorded"
            ),
        )
        if not self.enabled:
            discovery["requested"] = False
            verification["requested"] = False
            discovery["status"] = NOT_CALLED
            verification["status"] = NOT_CALLED
            discovery["failure_reason"] = "external_fallback_disabled_by_default"
            verification["failure_reason"] = "external_fallback_disabled_by_default"
        else:
            if discovery_requested:
                discovery = self._execute(
                    "discovery",
                    issue_id=_text(issue_id),
                    local_search_completion=local,
                    verification_reasons=reasons,
                    legal_query_terms=safe_terms,
                    query_ids=ids,
                    project_scope=scope,
                    trigger_reason=DISCOVERY_REASON,
                )
            if verification_requested:
                verification = self._execute(
                    "verification",
                    issue_id=_text(issue_id),
                    local_search_completion=local,
                    verification_reasons=reasons,
                    legal_query_terms=safe_terms,
                    query_ids=ids,
                    project_scope=scope,
                    trigger_reason="version_status_or_applicability_doubt",
                )

        all_records = [discovery, verification]
        for record in all_records:
            self._export_mode_status(record)
        requested_records = [record for record in all_records if record["requested"]]
        candidate_records = [candidate for record in all_records for candidate in record.get("candidates", [])]
        failures = [record["failure_reason"] for record in requested_records if record["status"] == FAILED and record.get("failure_reason")]
        pending = [record for record in requested_records if record["status"] in {PENDING_PROVIDER, PENDING_HUMAN_SCOPE, RUNNING}]
        if not requested_records:
            overall_status = NOT_CALLED
        elif failures:
            overall_status = FAILED
        elif pending:
            overall_status = "pending"
        elif candidate_records:
            overall_status = "hit"
        elif all(record["status"] == COMPLETED_NO_HIT for record in requested_records):
            overall_status = COMPLETED_NO_HIT
        else:
            overall_status = PENDING_HUMAN_SCOPE
        external_completed = bool(requested_records) and all(
            record["status"] in COMPLETED_STATUSES and record.get("external_search_completed")
            for record in requested_records
        )
        discovery_no_hit = discovery.get("status") == COMPLETED_NO_HIT and discovery.get("external_search_completed")
        no_applicable_independent_source = bool(
            local_complete_no_hit
            and local_no_applicable_eligible
            and discovery_no_hit
            and not candidate_records
            and external_completed
        )
        pending_reasons = [
            record.get("failure_reason")
            for record in requested_records
            if record.get("status") in {PENDING_PROVIDER, PENDING_HUMAN_SCOPE, RUNNING}
            and record.get("failure_reason")
        ]
        return {
            "schema_version": SCHEMA_VERSION,
            "enabled": self.enabled,
            "issue_id": _text(issue_id),
            # The nested copy is the canonical gate-facing location.  The
            # runtime root keeps the same object for backwards compatibility.
            "local_search_completion": local,
            "discovery": discovery,
            "verification": verification,
            "external_search_status": overall_status,
            "external_search_status_detail": (
                COMPLETED_WITH_CANDIDATES if overall_status == "hit" else overall_status
            ),
            "external_search_completed": external_completed,
            "dispatch_attempted": any(record.get("dispatch_attempted") for record in all_records),
            "provider_call_attempted": any(record.get("provider_call_attempted") for record in all_records),
            "http_called": any(record.get("http_called") for record in all_records),
            "http_call_count": sum(int(record.get("http_call_count") or 0) for record in all_records),
            "external_no_applicable_independent_source": no_applicable_independent_source,
            "external_failure_reason": "; ".join(dict.fromkeys(failures)),
            "external_pending_reasons": list(dict.fromkeys(pending_reasons)),
            "external_query_ids": list(dict.fromkeys(
                ids
                + [query_id for record in all_records for query_id in record.get("query_ids", [])]
            )),
            "configured_search_scope": list(dict.fromkeys(
                source_id
                for record in all_records
                for source_id in record.get("configured_search_scope", [])
            )),
            "executed_search_scope": list(dict.fromkeys(
                source_id
                for record in all_records
                for source_id in record.get("executed_search_scope", [])
            )),
            "candidates": candidate_records,
            "candidate_count": len(candidate_records),
            "candidate_independent_admission": "never_automatic; human source confirmation required",
            "cecn_policy": "candidate_only_not_sole_legal_basis",
            "local_explicit_satisfaction_preserved": bool(local_explicit_satisfaction),
            "rejected_query_count": len(rejected_terms),
            "rejected_query_reasons": rejected_terms,
            "manual_discovery_claim_allowed": bool(
                discovery.get("scope_completion_basis") == "human_attested_manual_discovery"
                and discovery.get("human_attested")
            ),
            "no_applicable_status_eligibility": {
                "local_search_status_required": COMPLETED_NO_HIT,
                "external_discovery_status_required": COMPLETED_NO_HIT,
                "external_search_completed_required": True,
                "scope_basis_required": ["provider_execution", "human_attested_manual_discovery"],
                "manifest_only_miss_is_eligible": False,
                "network_failure_is_eligible": False,
                "not_called_is_eligible": False,
            },
        }


def _is_level4_for_legal_basis(row: Mapping[str, Any]) -> bool:
    """Match the gate's explicit and legacy-inferred Level 4 definition."""

    return row.get("normative_level") == "Level 4" or (
        row.get("scope_classification") == "local_regional"
        and row.get("normative_level") not in {"Level 1", "Level 2", "Level 3"}
    )


def is_usable_legal_basis(row: Mapping[str, Any]) -> bool:
    """Return the canonical fail-closed legal-evidence admission decision.

    This is intentionally a pure metadata predicate.  It does not fetch,
    verify, or infer legal content.  The frozen local corpus may omit legacy
    optional fields such as ``retrieval_admission`` and ``verification_status``;
    however, an explicit null/false admission signal is rejected.  External
    candidates remain ineligible because their normalized metadata carries
    non-independent/pending status until a human source-confirmation record
    exists.
    """

    if not isinstance(row, Mapping):
        return False
    if not _text(row.get("source_locator")) or not _text(row.get("legal_quote")):
        return False
    # Independence is not inferred here: the primary field must be explicit.
    if row.get("independent_legal_evidence") is not True:
        return False
    # A missing legacy alias is compatible; an explicit false/null/non-True
    # alias is a denial and must override an older positive field.
    if "independent_evidence" in row and row.get("independent_evidence") is not True:
        return False
    if row.get("legal_evidence_eligibility") in _REJECTED_LEGAL_EVIDENCE_ELIGIBILITY:
        return False
    if "legal_evidence_eligibility" in row and row.get("legal_evidence_eligibility") is None:
        return False
    if row.get("retrieval_admission") in _REJECTED_RETRIEVAL_ADMISSIONS:
        return False
    if "retrieval_admission" in row and row.get("retrieval_admission") is None:
        return False
    if row.get("verification_status") in _UNVERIFIED_STATUSES:
        return False
    if "verification_status" in row and row.get("verification_status") is None:
        return False
    if row.get("source_role") == "practice_material_only":
        return False
    applicability_status = row.get("applicability_status")
    if _is_level4_for_legal_basis(row) and applicability_status != "matched":
        return False
    if applicability_status in _INAPPLICABLE_STATUSES:
        return False
    return True


def _is_usable_local_evidence(row: Mapping[str, Any]) -> bool:
    """Backwards-compatible Stage 3 name backed by the canonical predicate."""

    return is_usable_legal_basis(row)


def _reason_indicates_satisfaction(value: Any) -> bool:
    text = _text(value).lower()
    return any(marker in text for marker in (
        "满足", "符合要求", "未发现不一致", "未发现违规", "未违反", "satisfies", "complies", "no violation", "no inconsistency"
    ))


def build_local_search_completion(
    hierarchy_retrieval_audit: Mapping[str, Any],
    retrieved_legal_evidence: Iterable[Mapping[str, Any]],
    *,
    local_explicit_satisfaction: bool = False,
) -> dict[str, Any]:
    """Summarize whether strict local L1-4 search supports an external trigger."""

    levels = hierarchy_retrieval_audit.get("levels", []) if isinstance(hierarchy_retrieval_audit, Mapping) else []
    level_results: list[dict[str, Any]] = []
    executed_levels: list[str] = []
    blocked_scope_levels: list[str] = []
    phase_missing_facts: list[str] = []
    has_relevant_inconclusive = False
    observed_candidate_count = 0
    for record in levels:
        if not isinstance(record, Mapping):
            continue
        level = _text(record.get("level"))
        status = _text(record.get("status"))
        level_state = _text(record.get("level_state"))
        phase_results: list[dict[str, Any]] = []
        raw_phases = record.get("phases") if isinstance(record.get("phases"), list) else []
        for phase in raw_phases:
            if not isinstance(phase, Mapping):
                continue
            phase_results.append(
                {
                    "phase": _text(phase.get("phase")),
                    "retrieval_executed": phase.get("retrieval_executed")
                    if "retrieval_executed" in phase
                    else None,
                    "retrieval_status": _text(phase.get("retrieval_status"))
                    if "retrieval_status" in phase
                    else "",
                    "candidate_count": int(phase.get("candidate_count") or 0),
                    "triage_executed": bool(phase.get("triage_executed")),
                    "triage_status": _text(phase.get("triage_status")) or "not_called",
                    "failure_reason": _text(phase.get("failure_reason")),
                    "selected_chunk_ids": list(phase.get("selected_chunk_ids") or []),
                    "missing_elements": list(phase.get("missing_elements") or []),
                }
            )
        if level:
            level_results.append(
                {
                    "level": level,
                    "status": status,
                    "level_state": level_state,
                    "retrieval_executed": record.get("retrieval_executed")
                    if "retrieval_executed" in record
                    else None,
                    "retrieval_status": _text(record.get("retrieval_status"))
                    if "retrieval_status" in record
                    else "",
                    "failure_reason": _text(record.get("failure_reason")),
                    "phase_results": phase_results,
                }
            )
        if status == "completed":
            executed_levels.append(level)
        if level == "Level 4" and (
            status.startswith("blocked")
            or _text((record.get("applicability_gate") or {}).get("status")).startswith("blocked")
        ):
            blocked_scope_levels.append(level)
        if level_state == "relevant_but_inconclusive":
            has_relevant_inconclusive = True
        for phase in raw_phases:
            if not isinstance(phase, Mapping):
                continue
            observed_candidate_count += int(phase.get("candidate_count") or 0)
            phase_missing_facts.extend(
                _text(value)
                for value in phase.get("missing_elements", [])
                if _text(value)
            )
        observed_candidate_count += len(record.get("discovery_only_chunk_ids", []) or [])
    evidence = [dict(row) for row in retrieved_legal_evidence if isinstance(row, Mapping)]
    usable = [row for row in evidence if _is_usable_local_evidence(row)]
    stopped_at = _text(hierarchy_retrieval_audit.get("stopped_at_level")) if isinstance(hierarchy_retrieval_audit, Mapping) else ""
    stopped_at_is_real = stopped_at.lower() not in {"", "none", "null", "no_stop"}
    required_levels = {"Level 1", "Level 2", "Level 3", "Level 4"}

    def level_record_is_complete(row: Mapping[str, Any]) -> bool:
        """Require actual per-level/per-phase completion, not row presence."""

        if _text(row.get("status")) != "completed":
            return False
        if row.get("retrieval_executed") is False:
            return False
        if _text(row.get("retrieval_status")) in {
            "failed",
            "not_executed",
            "skipped_after_prior_level_failure",
            "skipped_after_higher_level_stop",
        }:
            return False
        if row.get("failure_reason"):
            return False
        phases = row.get("phase_results")
        if not isinstance(phases, list):
            # Backwards-compatible audit fixtures may only have a level row;
            # the strict runner always emits phase_results.
            return True
        for phase in phases:
            if not isinstance(phase, Mapping):
                return False
            if phase.get("retrieval_executed") is False:
                return False
            if _text(phase.get("retrieval_status")) in {
                "failed",
                "not_executed",
                "skipped_after_prior_level_failure",
                "skipped_after_higher_level_stop",
            }:
                return False
            if phase.get("failure_reason"):
                return False
            candidate_count = int(phase.get("candidate_count") or 0)
            triage_status = _text(phase.get("triage_status")) or "not_called"
            if candidate_count > 0 and triage_status != "completed":
                return False
            if phase.get("triage_executed") and triage_status != "completed":
                return False
        return True

    all_levels_seen = [row.get("level") for row in level_results]
    all_levels_executed = (
        len(level_results) == len(required_levels)
        and set(all_levels_seen) == required_levels
        and all(level_record_is_complete(row) for row in level_results)
        and not stopped_at_is_real
    )
    incomplete_levels = [
        _text(row.get("level"))
        for row in level_results
        if not level_record_is_complete(row)
    ]
    if blocked_scope_levels:
        status = PENDING_HUMAN_SCOPE
        completion_basis_detail = "level_4_scope_not_confirmed"
        completion_basis = "runtime_partial"
    elif stopped_at_is_real and usable:
        status = COMPLETED_WITH_CANDIDATES
        completion_basis_detail = "strict_cascade_stopped_on_usable_local_risk"
        completion_basis = "runtime_execution"
    elif all_levels_executed and usable:
        status = COMPLETED_WITH_CANDIDATES
        completion_basis_detail = "strict_level_1_to_4_local_search"
        completion_basis = "runtime_execution"
    elif all_levels_executed and observed_candidate_count > 0:
        status = COMPLETED_WITH_CANDIDATES
        completion_basis_detail = "strict_level_1_to_4_local_search_with_unusable_or_inconclusive_candidates"
        completion_basis = "runtime_execution"
    elif all_levels_executed:
        status = COMPLETED_NO_HIT
        completion_basis_detail = "strict_level_1_to_4_local_search_no_usable_basis"
        completion_basis = "runtime_execution"
    else:
        status = PENDING_HUMAN_SCOPE
        completion_basis_detail = "strict_local_search_not_complete"
        completion_basis = "runtime_partial"
    decisive_missing_facts = list(dict.fromkeys(phase_missing_facts))
    no_usable_basis = all_levels_executed and not usable
    fallback_eligible = bool(
        no_usable_basis
        and not local_explicit_satisfaction
        and not blocked_scope_levels
    )
    no_applicable_status_eligible = bool(
        fallback_eligible
        and status == COMPLETED_NO_HIT
        and observed_candidate_count == 0
        and not decisive_missing_facts
        and not has_relevant_inconclusive
    )
    return {
        "status": status,
        "executed_levels": executed_levels,
        "level_results": level_results,
        "all_levels_executed": all_levels_executed,
        "no_usable_applicable_basis": no_usable_basis,
        "fallback_discovery_eligible": fallback_eligible,
        "no_applicable_status_eligible": no_applicable_status_eligible,
        "usable_local_evidence_count": len(usable),
        "retrieved_local_evidence_count": len(evidence),
        "observed_candidate_count": observed_candidate_count,
        "decisive_missing_facts": decisive_missing_facts,
        "has_relevant_inconclusive": has_relevant_inconclusive,
        "blocked_scope_levels": blocked_scope_levels,
        "stopped_at_level": stopped_at or "none",
        "explicit_satisfaction_found": bool(local_explicit_satisfaction),
        "completion_basis": completion_basis,
        "completion_basis_detail": completion_basis_detail,
        "actual_completion": bool(all_levels_executed or (stopped_at_is_real and usable)),
        "level_completion_audit": {
            "required_levels": sorted(required_levels),
            "observed_levels": all_levels_seen,
            "incomplete_levels": incomplete_levels,
            "all_level_rows_completed": bool(
                len(level_results) == len(required_levels)
                and set(all_levels_seen) == required_levels
                and all(level_record_is_complete(row) for row in level_results)
            ),
            "stopped_at_is_real": stopped_at_is_real,
        },
        "failure_reason": (
            ""
            if all_levels_executed or (stopped_at_is_real and usable)
            else (
                "local_level_or_triage_failure_or_skip_present"
                if incomplete_levels
                else "local_level_cascade_incomplete"
            )
        ),
    }


def derive_verification_reasons(
    hierarchy_retrieval_audit: Mapping[str, Any],
    retrieved_legal_evidence: Iterable[Mapping[str, Any]],
    *,
    label_reasons: Iterable[Any] = (),
) -> list[str]:
    """Extract only explicit version/status/applicability doubts."""

    reasons = [_text(value) for value in label_reasons if _text(value)]
    for row in retrieved_legal_evidence:
        if not isinstance(row, Mapping):
            continue
        status = _text(row.get("applicability_status")).lower()
        role = _text(row.get("source_role")).lower()
        eligibility = _text(row.get("legal_evidence_eligibility")).lower()
        if "pending" in status or "unknown" in status or "blocked" in status:
            reasons.append(f"evidence_applicability_doubt:{_text(row.get('chunk_id'))}")
        if role in {"verification_pending", "verification_copy"} or eligibility == "verification_only":
            reasons.append(f"source_status_or_version_doubt:{_text(row.get('chunk_id'))}")
    for record in (hierarchy_retrieval_audit.get("levels", []) if isinstance(hierarchy_retrieval_audit, Mapping) else []):
        if not isinstance(record, Mapping):
            continue
        if _text(record.get("level")) == "Level 4" and _text(record.get("status")).startswith("blocked"):
            reasons.append("local_level4_scope_mismatch_or_missing_jurisdiction")
    return list(dict.fromkeys(reason for reason in reasons if reason))


__all__ = [
    "COMPLETED_NO_HIT",
    "COMPLETED_WITH_CANDIDATES",
    "DISCOVERY_REASON",
    "ExternalFallbackStateMachine",
    "ExternalProvider",
    "ExternalRequest",
    "FAILED",
    "FIVE_STATE_EXPORTS",
    "ManifestHttpProvider",
    "NOT_CALLED",
    "PENDING_HUMAN_SCOPE",
    "PENDING_PROVIDER",
    "ProviderResponse",
    "build_local_search_completion",
    "derive_verification_reasons",
    "is_usable_legal_basis",
    "load_external_manifest",
    "normalize_external_candidate",
    "sanitize_legal_query_terms",
    "sha256_text",
    "validate_public_allowlisted_url",
]
