"""Read-only Neon connectivity probe.

Usage:
    python scripts/neon_probe.py --from-env [VAR] --purpose runtime|migration [--skip-inspection]
    python scripts/neon_probe.py --from-clipboard --purpose runtime|migration [--skip-inspection]
    python scripts/neon_probe.py --stdin --purpose runtime|migration [--skip-inspection]
    python scripts/neon_probe.py --purpose runtime|migration [--skip-inspection]

Exactly one input method is accepted. A variable read through ``--from-env`` is
deleted from the environment immediately. Output is limited to the marker
contract, fixed-text stage lines and redacted exception text: the URL, host,
user, password, database name, table names and IP addresses are never printed.
Every inspection query passes the SELECT/SHOW allowlist and runs inside a
read-only transaction. No DDL, no DML, no migrations.
"""

from __future__ import annotations

import asyncio
import getpass
import json
import os
import socket
import ssl
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db_url import (  # noqa: E402
    DriverConfig,
    SqlNotAllowed,
    UrlFacts,
    UrlValidationError,
    assert_read_only_sql,
    build_driver_config,
    redact,
    validate_connection_url,
)
from backend.app.schema_expectations import (  # noqa: E402
    compare_tables,
    discover_revision_paths,
    expected_head_revision,
    expected_tables,
)

CONTRACT_KEYS = (
    "PROBE_PURPOSE",
    "URL_VALIDATION",
    "HOST_FORMAT",
    "POOLED",
    "DNS_SYSTEM",
    "DNS_GOOGLE",
    "DNS_CLOUDFLARE",
    "DNS_DOH",
    "TCP",
    "TLS",
    "ASYNCPG_SELECT_1",
    "SQLALCHEMY_SELECT_1",
    "FAILURE_CLASS",
    "COLD_START_RETRY_USED",
)

INSPECTION_KEYS = (
    "NEON_READ_ONLY_INSPECTION",
    "PG_SERVER_VERSION",
    "PG_TABLE_COUNT",
    "PG_EXPECTED_TABLE_COUNT",
    "PG_MISSING_COUNT",
    "PG_UNEXPECTED_COUNT",
    "NEON_SCHEMA_STATUS",
    "NEON_ALEMBIC_STATUS",
)

USAGE = (
    "usage: neon_probe.py (--from-env [VAR] | --from-clipboard | --stdin) "
    "--purpose runtime|migration [--skip-inspection]\n"
    "       neon_probe.py --purpose runtime|migration [--skip-inspection]"
    "   # interactive hidden prompt"
)

INTERACTIVE_HINT = (
    "Paste with right-click, or Ctrl+Shift+V in Windows Terminal. "
    "Nothing will be echoed. If it stays empty, use --from-env."
)

DEFAULT_ENV_VAR = "NEON_PROBE_URL"
SYSTEM_SCHEMAS = {"pg_catalog", "information_schema", "pg_toast"}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

@dataclass
class CliOptions:
    methods: list[tuple[str, str | None]] = field(default_factory=list)
    purpose: str = ""
    skip_inspection: bool = False


def parse_cli(argv: list[str]) -> tuple[CliOptions | None, str | None]:
    """Return ``(options, error)``; error is a stable BLOCKED_* code."""
    methods: list[tuple[str, str | None]] = []
    purpose: str | None = None
    skip = False
    index = 0

    while index < len(argv):
        argument = argv[index]
        if argument in ("-h", "--help"):
            return None, "HELP"
        if argument == "--skip-inspection":
            skip = True
            index += 1
            continue
        if argument == "--purpose":
            if index + 1 >= len(argv):
                return None, "BLOCKED_MISSING_PURPOSE"
            purpose = argv[index + 1].lower()
            index += 2
            continue
        if argument.startswith("--purpose="):
            purpose = argument.split("=", 1)[1].lower()
            index += 1
            continue
        if argument == "--from-env":
            variable = DEFAULT_ENV_VAR
            if index + 1 < len(argv) and not argv[index + 1].startswith("--"):
                variable = argv[index + 1]
                index += 1
            methods.append(("env", variable))
            index += 1
            continue
        if argument.startswith("--from-env="):
            methods.append(("env", argument.split("=", 1)[1]))
            index += 1
            continue
        if argument == "--from-clipboard":
            methods.append(("clipboard", None))
            index += 1
            continue
        if argument == "--stdin":
            methods.append(("stdin", None))
            index += 1
            continue
        return None, "BLOCKED_UNKNOWN_ARGUMENT"

    if purpose not in ("runtime", "migration"):
        return None, "BLOCKED_MISSING_PURPOSE"
    return CliOptions(methods=methods, purpose=purpose, skip_inspection=skip), None


def resolve_input_method(
    methods: list[tuple[str, str | None]], interactive_allowed: bool
) -> tuple[str | None, str | None, str | None]:
    """Pick exactly one input method, or explain why none can be used."""
    if len(methods) > 1:
        return None, None, "BLOCKED_AMBIGUOUS_INPUT"
    if len(methods) == 1:
        return methods[0][0], methods[0][1], None
    if not interactive_allowed:
        return None, None, "BLOCKED_AMBIGUOUS_INPUT"
    return "interactive", None, None


# --------------------------------------------------------------------------- #
# Input methods
# --------------------------------------------------------------------------- #

def read_url_from_env(variable: str) -> tuple[str, str]:
    sentinel = object()
    value = os.environ.pop(variable, sentinel)
    if value is sentinel:
        return "", "BLOCKED_ENV_MISSING"
    text = str(value).strip()
    if not text:
        return "", "BLOCKED_ENV_EMPTY"
    return text, "PASS"


def read_url_from_clipboard() -> tuple[str, str]:
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "Get-Clipboard -Raw",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:  # noqa: BLE001 - powershell missing or timed out
        return "", "BLOCKED_CLIPBOARD_ACCESS"
    if result.returncode != 0:
        return "", "BLOCKED_CLIPBOARD_ACCESS"
    text = (result.stdout or "").strip()
    if not text:
        return "", "BLOCKED_EMPTY_CLIPBOARD"
    if "\n" in text or "\r" in text:
        return "", "BLOCKED_INVALID_URL"
    if not text.lower().startswith(
        ("postgres://", "postgresql://", "postgresql+asyncpg://", "postgresql+psycopg2://")
    ):
        return "", "BLOCKED_INVALID_URL"
    return text, "PASS"


def read_url_from_stdin(stream=None) -> tuple[str, str]:
    source = stream if stream is not None else sys.stdin
    is_tty = bool(getattr(source, "isatty", lambda: False)())
    if is_tty:
        print(
            "Reading the connection URL from stdin; paste it and press Enter.",
            file=sys.stderr,
        )
    line = source.readline()
    text = (line or "").strip().strip('"').strip("'")
    if not text:
        return "", "BLOCKED_EMPTY_INPUT"
    return text, "PASS"


def read_url_interactive() -> tuple[str, str]:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return "", "BLOCKED_NO_TTY"
    for _ in range(3):
        try:
            raw = getpass.getpass(INTERACTIVE_HINT + "\n> ")
        except KeyboardInterrupt:
            return "", "BLOCKED_INTERRUPTED"
        except EOFError:
            return "", "BLOCKED_NO_CONSOLE_INPUT"
        text = (raw or "").strip().strip('"').strip("'")
        if text:
            return text, "PASS"
        print("INPUT_EMPTY=RETRY")
    print("RETRY_COMMAND=$env:NEON_PROBE_URL = (Get-Clipboard -Raw).Trim()")
    print("RETRY_COMMAND=python scripts/neon_probe.py --from-env --purpose runtime")
    return "", "BLOCKED_EMPTY_INPUT"


# --------------------------------------------------------------------------- #
# Network layers
# --------------------------------------------------------------------------- #

def _dns_powershell(host: str, server: str) -> str:
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "Resolve-DnsName",
                "-Name",
                host,
                "-Server",
                server,
                "-DnsOnly",
                "-Type",
                "A",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except Exception:  # noqa: BLE001
        return "FAIL"
    if result.returncode != 0:
        return "FAIL"
    output = (result.stdout or "").lower()
    if not output.strip() or "does not exist" in output or "could not" in output:
        return "FAIL"
    return "PASS"


def _dns_doh(host: str) -> str:
    query = urllib.parse.urlencode({"name": host, "type": "A"})
    request = urllib.request.Request(
        "https://cloudflare-dns.com/dns-query?" + query,
        headers={"accept": "application/dns-json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return "FAIL"
    if payload.get("Status") == 0 and payload.get("Answer"):
        return "PASS"
    return "FAIL"


def _tcp(host: str, port: int) -> tuple[str, BaseException | None]:
    try:
        with socket.create_connection((host, port), timeout=10):
            return "PASS", None
    except Exception as exc:  # noqa: BLE001
        return "FAIL", exc


def _tls(host: str, port: int) -> tuple[str, BaseException | None]:
    context = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=10) as raw:
            with context.wrap_socket(raw, server_hostname=host):
                return "PASS", None
    except Exception as exc:  # noqa: BLE001
        return "FAIL", exc


def classify_failure(exc: BaseException | None) -> str:
    if exc is None:
        return "NONE"
    name = type(exc).__name__
    if isinstance(exc, UrlValidationError):
        return "URL_PARSE"
    if isinstance(exc, socket.gaierror):
        if getattr(exc, "errno", None) == getattr(socket, "EAI_NONAME", -2):
            return "DNS_NXDOMAIN"
        return "DNS_OTHER"
    if isinstance(exc, ssl.SSLError) or name in {"SSLError", "CertificateError"}:
        return "TLS"
    if isinstance(exc, ConnectionRefusedError):
        return "TCP_REFUSED"
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, socket.timeout)):
        return "TIMEOUT"
    if name in {
        "InvalidPasswordError",
        "InvalidAuthorizationSpecificationError",
        "InsufficientPrivilegeError",
        "CannotConnectNowError",
    }:
        return "AUTH"
    if name == "InvalidCatalogNameError":
        return "DB_NOT_FOUND"
    if name in {"PostgresError", "UndefinedTableError", "SyntaxOrAccessError"}:
        return "QUERY"
    if isinstance(exc, OSError):
        message = str(exc).lower()
        if "refused" in message:
            return "TCP_REFUSED"
        if "timed out" in message:
            return "TCP_TIMEOUT"
    return "UNKNOWN"


async def _with_retry(factory, timeout: float = 35.0):
    """Run once; on timeout wait 5s and try once more (Neon cold start)."""
    try:
        return await asyncio.wait_for(factory(), timeout=timeout), False, None
    except (asyncio.TimeoutError, TimeoutError) as first:
        try:
            await asyncio.sleep(5)
            return await asyncio.wait_for(factory(), timeout=timeout), True, None
        except Exception as second:  # noqa: BLE001
            return None, True, second
    except Exception as exc:  # noqa: BLE001
        return None, False, exc


async def _asyncpg_once(cfg: DriverConfig):
    import asyncpg

    connection = await asyncpg.connect(**cfg.asyncpg_kwargs)
    try:
        return await connection.fetchval("SELECT 1")
    finally:
        await connection.close()


async def _sqlalchemy_once(cfg: DriverConfig):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(
        cfg.url,
        echo=False,
        pool_pre_ping=True,
        connect_args=cfg.sqlalchemy_connect_args,
    )
    try:
        async with engine.connect() as connection:
            return (await connection.execute(text("SELECT 1"))).scalar()
    finally:
        await engine.dispose()


# --------------------------------------------------------------------------- #
# Inspection
# --------------------------------------------------------------------------- #

async def _execute(connection, sql: str):
    assert_read_only_sql(sql)
    from sqlalchemy import text

    return await connection.execute(text(sql))


async def _inspect(cfg: DriverConfig, markers: dict[str, str]) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    revision_paths = discover_revision_paths(ROOT / "migrations" / "versions")
    expected = expected_tables(revision_paths)
    head = expected_head_revision(revision_paths)
    markers["PG_EXPECTED_TABLE_COUNT"] = str(len(expected))

    engine = create_async_engine(
        cfg.url,
        echo=False,
        pool_pre_ping=True,
        connect_args=cfg.sqlalchemy_connect_args,
    )
    try:
        async with engine.connect() as connection:
            # Control statement, not an inspection query: it can only restrict.
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            read_only = (await _execute(connection, "SHOW transaction_read_only")).scalar()
            if str(read_only).lower() != "on":
                markers["NEON_READ_ONLY_INSPECTION"] = "FAIL"
                return

            version = (
                await _execute(connection, "SELECT current_setting('server_version')")
            ).scalar()
            markers["PG_SERVER_VERSION"] = ".".join(
                str(version or "").replace("-", ".").split(".")[:2]
            )

            schema_rows = (
                await _execute(connection, "SELECT schema_name FROM information_schema.schemata")
            ).all()
            app_schemas = {
                row[0] for row in schema_rows if row[0] not in SYSTEM_SCHEMAS
            }
            database = (await _execute(connection, "SELECT current_database()")).scalar()

            table_rows = (
                await _execute(
                    connection,
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'",
                )
            ).all()
            tables = {row[0] for row in table_rows}

            if "alembic_version" in tables:
                current = (
                    await _execute(connection, "SELECT version_num FROM alembic_version")
                ).scalar()
                markers["NEON_ALEMBIC_STATUS"] = (
                    "MATCHED" if head is not None and current == head else "DIFFERENT"
                )
            else:
                markers["NEON_ALEMBIC_STATUS"] = "ABSENT"

            comparison = compare_tables(expected, tables)
            markers["PG_TABLE_COUNT"] = str(len(tables))
            markers["PG_MISSING_COUNT"] = str(len(comparison.missing))
            markers["PG_UNEXPECTED_COUNT"] = str(len(comparison.unexpected))

            if not tables and markers["NEON_ALEMBIC_STATUS"] == "ABSENT":
                markers["NEON_SCHEMA_STATUS"] = "EMPTY"
            elif expected and expected <= tables:
                markers["NEON_SCHEMA_STATUS"] = "EXISTING"
            elif (tables & expected) or "alembic_version" in tables:
                markers["NEON_SCHEMA_STATUS"] = "PARTIAL"
            else:
                markers["NEON_SCHEMA_STATUS"] = "UNKNOWN"

            if not database or not app_schemas:
                markers["NEON_SCHEMA_STATUS"] = markers.get("NEON_SCHEMA_STATUS", "UNKNOWN")
            markers["NEON_READ_ONLY_INSPECTION"] = "PASS"
    finally:
        await engine.dispose()


# --------------------------------------------------------------------------- #
# Flow
# --------------------------------------------------------------------------- #

def _base_markers(purpose: str) -> dict[str, str]:
    return {
        "PROBE_PURPOSE": purpose,
        "URL_VALIDATION": "NOT_STARTED",
        "HOST_FORMAT": "NOT_STARTED",
        "POOLED": "false",
        "DNS_SYSTEM": "NOT_STARTED",
        "DNS_GOOGLE": "NOT_STARTED",
        "DNS_CLOUDFLARE": "NOT_STARTED",
        "DNS_DOH": "NOT_STARTED",
        "TCP": "NOT_STARTED",
        "TLS": "NOT_STARTED",
        "ASYNCPG_SELECT_1": "NOT_STARTED",
        "SQLALCHEMY_SELECT_1": "NOT_STARTED",
        "FAILURE_CLASS": "NONE",
        "COLD_START_RETRY_USED": "false",
    }


def _emit(markers: dict[str, str]) -> None:
    for key in CONTRACT_KEYS:
        print(f"{key}={markers.get(key, 'NOT_STARTED')}")
    for key in INSPECTION_KEYS:
        if key in markers:
            print(f"{key}={markers[key]}")


def _report_error(exc: BaseException, url_text: str) -> None:
    print(f"ERROR_CLASS={type(exc).__name__}")
    print("ERROR_MESSAGE=" + redact(str(exc), url_text))


async def _flow(options: CliOptions, url_text: str, markers: dict[str, str]) -> int:
    print("STAGE=L1_URL_VALIDATION")
    try:
        facts: UrlFacts = validate_connection_url(url_text)
    except UrlValidationError as exc:
        markers["URL_VALIDATION"] = "FAIL"
        markers["FAILURE_CLASS"] = "URL_PARSE"
        print("ERROR_CLASS=UrlValidationError")
        print(f"ERROR_CODE={exc.code}")
        return 1

    markers["URL_VALIDATION"] = "PASS"
    markers["HOST_FORMAT"] = facts.host_format
    markers["POOLED"] = "true" if facts.pooled else "false"
    print("SCHEME_OK=true")
    print(f"PORT_SOURCE={facts.port_source}")
    print(f"PORT_CHECK={facts.port_check}")
    print(f"SSL_CONFIGURED={'true' if facts.ssl_configured else 'false'}")
    if facts.host_format == "WARN":
        print("WARN=HOST_NOT_NEON_DOMAIN")
    if facts.port_check != "PASS":
        print("WARN=NON_STANDARD_PORT")
    if options.purpose == "migration" and facts.pooled:
        print("WARN=POOLED_ENDPOINT_WITH_MIGRATION_PURPOSE")
    if options.purpose == "runtime" and not facts.pooled:
        print("WARN=DIRECT_ENDPOINT_WITH_RUNTIME_PURPOSE")

    cfg = build_driver_config(facts)
    for name in cfg.dropped_params:
        print(f"DROPPED_PARAM={name}")

    print("STAGE=L2_DNS")
    if facts.host_is_ip:
        markers["DNS_SYSTEM"] = "PASS"
        print("DNS_SYSTEM_SOURCE=IP_LITERAL")
    else:
        dns_exc: BaseException | None = None
        try:
            infos = socket.getaddrinfo(
                facts.url.host, facts.port, socket.AF_UNSPEC, socket.SOCK_STREAM
            )
            {item[4][0] for item in infos}
            markers["DNS_SYSTEM"] = "PASS"
        except Exception as exc:  # noqa: BLE001
            markers["DNS_SYSTEM"] = "FAIL"
            dns_exc = exc
        markers["DNS_GOOGLE"] = _dns_powershell(facts.url.host, "8.8.8.8")
        markers["DNS_CLOUDFLARE"] = _dns_powershell(facts.url.host, "1.1.1.1")
        markers["DNS_DOH"] = _dns_doh(facts.url.host)
        if markers["DNS_SYSTEM"] != "PASS":
            external = {
                markers["DNS_GOOGLE"],
                markers["DNS_CLOUDFLARE"],
                markers["DNS_DOH"],
            }
            markers["FAILURE_CLASS"] = "DNS_NXDOMAIN" if external == {"FAIL"} else "DNS_OTHER"
            if dns_exc is not None:
                _report_error(dns_exc, url_text)
            return 1

    print("STAGE=L3_TCP")
    tcp_status, tcp_exc = _tcp(facts.url.host, facts.port)
    markers["TCP"] = tcp_status
    if tcp_status != "PASS":
        markers["FAILURE_CLASS"] = classify_failure(tcp_exc)
        if tcp_exc is not None:
            _report_error(tcp_exc, url_text)
        return 1

    print("STAGE=L4_TLS")
    tls_status, tls_exc = _tls(facts.url.host, facts.port)
    markers["TLS"] = tls_status
    if tls_status != "PASS":
        markers["FAILURE_CLASS"] = "TLS"
        if tls_exc is not None:
            _report_error(tls_exc, url_text)
        return 1

    print("STAGE=L5_ASYNCPG")
    value, retried, exc = await _with_retry(lambda: _asyncpg_once(cfg))
    markers["COLD_START_RETRY_USED"] = "true" if retried else "false"
    if exc is not None or value != 1:
        markers["ASYNCPG_SELECT_1"] = "FAIL"
        markers["FAILURE_CLASS"] = classify_failure(exc) if exc is not None else "QUERY"
        if exc is not None:
            _report_error(exc, url_text)
        return 1
    markers["ASYNCPG_SELECT_1"] = "PASS"

    print("STAGE=L6_SQLALCHEMY")
    engine_value, engine_retried, engine_exc = await _with_retry(
        lambda: _sqlalchemy_once(cfg)
    )
    markers["COLD_START_RETRY_USED"] = (
        "true" if (retried or engine_retried) else "false"
    )
    if engine_exc is not None or engine_value != 1:
        markers["SQLALCHEMY_SELECT_1"] = "FAIL"
        markers["FAILURE_CLASS"] = (
            classify_failure(engine_exc) if engine_exc is not None else "QUERY"
        )
        print("CONFIG_BUG_IN_SQLALCHEMY_LAYER")
        if engine_exc is not None:
            _report_error(engine_exc, url_text)
        return 1
    markers["SQLALCHEMY_SELECT_1"] = "PASS"

    if options.skip_inspection:
        return 0

    print("STAGE=L7_READ_ONLY_INSPECTION")
    try:
        await _inspect(cfg, markers)
    except SqlNotAllowed as exc:
        markers["NEON_READ_ONLY_INSPECTION"] = "FAIL"
        markers["FAILURE_CLASS"] = "QUERY"
        print(f"ERROR_CLASS=SqlNotAllowed")
        print(f"ERROR_CODE={exc.reason}")
        return 1
    except Exception as exc:  # noqa: BLE001
        markers["NEON_READ_ONLY_INSPECTION"] = "FAIL"
        markers["FAILURE_CLASS"] = classify_failure(exc)
        _report_error(exc, url_text)
        return 1
    return 0


async def _probe(options: CliOptions, url_text: str) -> int:
    markers = _base_markers(options.purpose)
    try:
        return await _flow(options, url_text, markers)
    except Exception as exc:  # noqa: BLE001 - never leak a traceback
        markers["FAILURE_CLASS"] = "UNKNOWN"
        _report_error(exc, url_text)
        return 1
    finally:
        _emit(markers)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main() -> int:
    options, error = parse_cli(sys.argv[1:])
    if error == "HELP":
        print(USAGE)
        return 0
    if options is None:
        print(USAGE)
        print(error)
        return 2

    interactive_allowed = bool(sys.stdin.isatty() and sys.stdout.isatty())
    method, variable, method_error = resolve_input_method(
        options.methods, interactive_allowed
    )
    if method_error:
        print(USAGE)
        print(method_error)
        return 2

    if method == "env":
        url_text, read_error = read_url_from_env(variable or DEFAULT_ENV_VAR)
        print("INPUT_SOURCE=env")
    elif method == "clipboard":
        url_text, read_error = read_url_from_clipboard()
        print("INPUT_SOURCE=clipboard")
    elif method == "stdin":
        url_text, read_error = read_url_from_stdin()
        print("INPUT_SOURCE=stdin")
    else:
        url_text, read_error = read_url_interactive()
        print("INPUT_SOURCE=interactive")

    if read_error != "PASS":
        print(read_error)
        return 2

    try:
        return asyncio.run(_probe(options, url_text))
    except KeyboardInterrupt:
        print("BLOCKED_INTERRUPTED")
        return 2


if __name__ == "__main__":
    sys.exit(main())
