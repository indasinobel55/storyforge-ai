"""Pure PostgreSQL connection-URL helpers.

This module performs no I/O, reads no environment variables and creates no
engines, so it can be unit tested offline and reused by the probe today and by
the API/Alembic in later stages. There is exactly one implementation of
validation, driver translation and secret redaction.

Nothing here ever prints anything; callers decide what to emit.
"""

from __future__ import annotations

import ipaddress
import re
import ssl
from dataclasses import dataclass
from urllib.parse import quote, quote_plus

from sqlalchemy.engine import URL, make_url

ALLOWED_DRIVERS = ("postgres", "postgresql", "postgresql+asyncpg", "postgresql+psycopg2")
ASYNC_DRIVER = "postgresql+asyncpg"
DEFAULT_PORT = 5432
NEON_SUFFIX = ".neon.tech"
POOLER_MARKER = "-pooler"
LIBPQ_ONLY_TLS_PARAMS = ("sslmode", "channel_binding", "ssl")
READ_ONLY_KEYWORDS = frozenset({"SELECT", "SHOW"})
_URL_PREFIXES = (
    "postgres://",
    "postgresql://",
    "postgresql+asyncpg://",
    "postgresql+psycopg2://",
)

_GENERIC_URL_RE = re.compile(r"postgres(?:ql)?(?:\+[A-Za-z0-9_]+)?://\S+", re.IGNORECASE)
_NEON_HOST_RE = re.compile(r"[A-Za-z0-9._-]+\.neon\.tech", re.IGNORECASE)
_PASSWORD_ASSIGN_RE = re.compile(r"(?i)\b(password|passwd|pwd)\s*=\s*\S+")
_IPV4_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


class UrlValidationError(ValueError):
    """Validation failure carrying a stable, non-secret reason code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class SqlNotAllowed(ValueError):
    """Raised when a statement is not a single read-only SELECT/SHOW."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class UrlFacts:
    url: URL
    driver: str
    host_format: str  # PASS | WARN
    host_is_ip: bool
    pooled: bool
    port: int
    port_source: str  # EXPLICIT | DEFAULT
    port_check: str  # PASS | WARN_NON_STANDARD
    ssl_configured: bool
    ssl_mode: str
    database_present: bool


@dataclass(frozen=True)
class DriverConfig:
    url: URL
    sqlalchemy_connect_args: dict
    asyncpg_kwargs: dict
    dropped_params: tuple[str, ...]
    ssl_mode: str
    ssl_context_required: bool
    prepared_cache_disabled: bool


def _first(value):
    if isinstance(value, (tuple, list)):
        return str(value[0]) if value else ""
    return "" if value is None else str(value)


def normalize_scheme(raw: str) -> str:
    """Map the libpq ``postgres://`` alias onto SQLAlchemy's spelling."""
    text = (raw or "").strip()
    if text.lower().startswith("postgres://"):
        return "postgresql://" + text[len("postgres://") :]
    return text


def validate_connection_url(raw: str) -> UrlFacts:
    """Validate a PostgreSQL URL without touching the network.

    Multiline input is rejected so clipboard content cannot smuggle a second
    statement or an unrelated line. A non-Neon hostname is only a warning:
    Neon hostname shapes have changed over time.
    """
    text = (raw or "").strip().strip('"').strip("'")
    if not text:
        raise UrlValidationError("BLOCKED_EMPTY_INPUT")
    if "\n" in text or "\r" in text:
        raise UrlValidationError("BLOCKED_MULTILINE_INPUT")
    lowered = text.lower()
    if not lowered.startswith(_URL_PREFIXES):
        raise UrlValidationError("BLOCKED_NOT_POSTGRESQL")
    try:
        parsed = make_url(normalize_scheme(text))
    except Exception:  # noqa: BLE001 - normalized to a stable code
        raise UrlValidationError("URL_PARSE") from None
    if parsed.drivername not in ALLOWED_DRIVERS:
        raise UrlValidationError("URL_WRONG_SCHEME")
    if not parsed.username:
        raise UrlValidationError("URL_MISSING_USERNAME")
    if parsed.password is None:
        raise UrlValidationError("URL_MISSING_PASSWORD")
    if not parsed.host:
        raise UrlValidationError("URL_MISSING_HOST")
    if not parsed.database:
        raise UrlValidationError("URL_MISSING_DATABASE")

    host = parsed.host
    try:
        ipaddress.ip_address(host)
        host_is_ip = True
    except ValueError:
        host_is_ip = False

    first_label = host.split(".")[0].lower()
    explicit_port = parsed.port is not None
    port = parsed.port or DEFAULT_PORT
    ssl_mode = (
        _first(parsed.query.get("sslmode")) or _first(parsed.query.get("ssl")) or "require"
    ).lower()

    return UrlFacts(
        url=parsed,
        driver=parsed.drivername,
        host_format="PASS" if host.lower().endswith(NEON_SUFFIX) else "WARN",
        host_is_ip=host_is_ip,
        pooled=POOLER_MARKER in first_label,
        port=port,
        port_source="EXPLICIT" if explicit_port else "DEFAULT",
        port_check="PASS" if port == DEFAULT_PORT else "WARN_NON_STANDARD",
        ssl_configured=("sslmode" in parsed.query or "ssl" in parsed.query),
        ssl_mode=ssl_mode,
        database_present=bool(parsed.database),
    )


def build_driver_config(facts: UrlFacts) -> DriverConfig:
    """Translate libpq-style TLS parameters into asyncpg-compatible settings.

    ``sslmode`` and ``channel_binding`` are libpq parameters that asyncpg
    rejects as URL query options, so they are removed and replaced by a real
    ``ssl.SSLContext``. For pooled endpoints the prepared-statement cache is
    disabled (PgBouncer transaction mode does not support it).
    """
    parsed = facts.url
    dropped = tuple(name for name in LIBPQ_ONLY_TLS_PARAMS if name in parsed.query)
    query = {key: value for key, value in parsed.query.items() if key not in dropped}
    prepared_cache_disabled = bool(facts.pooled)
    if prepared_cache_disabled:
        # Verified against the installed SQLAlchemy asyncpg dialect: this is a
        # dialect URL option that is translated into asyncpg's DBAPI argument.
        query["prepared_statement_cache_size"] = "0"

    engine_url = URL.create(
        drivername=ASYNC_DRIVER,
        username=parsed.username,
        password=parsed.password,
        host=parsed.host,
        port=facts.port,
        database=parsed.database,
        query=query,
    )

    if facts.ssl_mode == "disable":
        ssl_setting: object = False
        context_required = False
    else:
        ssl_setting = ssl.create_default_context()
        context_required = True

    sqlalchemy_connect_args: dict = {"timeout": 30, "ssl": ssl_setting}
    asyncpg_kwargs: dict = {
        "host": parsed.host,
        "port": facts.port,
        "user": parsed.username,
        "password": parsed.password,
        "database": parsed.database,
        "timeout": 30,
        "ssl": ssl_setting,
    }
    if prepared_cache_disabled:
        asyncpg_kwargs["statement_cache_size"] = 0

    return DriverConfig(
        url=engine_url,
        sqlalchemy_connect_args=sqlalchemy_connect_args,
        asyncpg_kwargs=asyncpg_kwargs,
        dropped_params=dropped,
        ssl_mode=facts.ssl_mode,
        ssl_context_required=context_required,
        prepared_cache_disabled=prepared_cache_disabled,
    )


def collect_secrets(url_text: str) -> tuple[str, ...]:
    """Every string derived from the URL that must never be printed."""
    secrets: list[str] = []

    def add(value: object) -> None:
        text = "" if value is None else str(value)
        if text and text not in secrets:
            secrets.append(text)

    add((url_text or "").strip())
    try:
        parsed = make_url(normalize_scheme((url_text or "").strip()))
    except Exception:  # noqa: BLE001 - best effort
        return tuple(sorted(secrets, key=len, reverse=True))

    add(parsed.render_as_string(hide_password=False))
    for value in (parsed.username, parsed.password):
        if value:
            add(value)
            add(quote(str(value), safe=""))
            add(quote_plus(str(value), safe=""))
    if parsed.username and parsed.password:
        pair = f"{parsed.username}:{parsed.password}"
        add(pair)
        add(quote(pair, safe=""))
        add(quote_plus(pair, safe=""))
    if parsed.host:
        add(parsed.host)
    return tuple(sorted(secrets, key=len, reverse=True))


def redact(message: str, url_text: str | None = None, extra: tuple[str, ...] = ()) -> str:
    """Remove URL, credentials, host and address literals from a message."""
    text = "" if message is None else str(message)
    secrets = list(collect_secrets(url_text)) if url_text else []
    secrets.extend(str(item) for item in extra if item)
    for secret in sorted(set(secrets), key=len, reverse=True):
        if len(secret) >= 3:
            text = text.replace(secret, "<redacted>")
    text = _GENERIC_URL_RE.sub("<redacted>", text)
    text = _NEON_HOST_RE.sub("<redacted>", text)
    text = _PASSWORD_ASSIGN_RE.sub("<redacted>", text)
    text = _IPV4_RE.sub("<redacted>", text)
    return " ".join(text.split())[:300]


def strip_leading_comments(sql: str) -> str:
    """Drop leading whitespace and ``--`` / ``/* */`` comments."""
    text = sql or ""
    while True:
        stripped = text.lstrip()
        if stripped.startswith("--"):
            newline = stripped.find("\n")
            text = "" if newline < 0 else stripped[newline + 1 :]
        elif stripped.startswith("/*"):
            end = stripped.find("*/")
            if end < 0:
                return ""
            text = stripped[end + 2 :]
        else:
            return stripped


def leading_keyword(sql: str) -> str:
    match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)", strip_leading_comments(sql))
    return match.group(1).upper() if match else ""


def assert_read_only_sql(sql: str) -> str:
    """Accept exactly one SELECT or SHOW statement; reject everything else."""
    keyword = leading_keyword(sql)
    if keyword not in READ_ONLY_KEYWORDS:
        raise SqlNotAllowed(keyword or "UNKNOWN")
    body = strip_leading_comments(sql).strip().rstrip(";").strip()
    if ";" in body:
        raise SqlNotAllowed("MULTI_STATEMENT")
    if keyword == "SELECT" and re.search(
        r"(?i)\b(INTO|FOR\s+UPDATE|FOR\s+SHARE)\b", body
    ):
        raise SqlNotAllowed("WRITE_CLAUSE")
    return sql


def is_read_only_sql(sql: str) -> bool:
    try:
        assert_read_only_sql(sql)
    except SqlNotAllowed:
        return False
    return True
