"""Offline tests for the Neon probe, URL helpers and revision parser.

No network is used: URLs are obviously fake, the loopback probe test talks only
to 127.0.0.1, and clipboard access is never exercised.
"""

from __future__ import annotations

import os
import ssl
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, quote_plus

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import neon_probe  # noqa: E402

from backend.app.db_url import (  # noqa: E402
    SqlNotAllowed,
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
    orm_table_names,
)

PROBE = SCRIPTS / "neon_probe.py"
FAKE_PASSWORD = "fakepass"
POOLED_URL = (
    "postgresql://fakeuser:fakepass@ep-test-123-pooler.us-east-2.aws.neon.tech:5432"
    "/neondb?sslmode=require&channel_binding=require"
)
DIRECT_URL = "postgresql://fakeuser:fakepass@ep-test-123.us-east-2.aws.neon.tech/neondb"
LOOPBACK_URL = "postgresql://fakeuser:fakepass-loop@127.0.0.1:1/neondb"


def _run_probe(args, env_extra=None, timeout=120):
    environment = os.environ.copy()
    environment.pop("NEON_PROBE_URL", None)
    environment.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(PROBE), *args],
        cwd=str(ROOT),
        env=environment,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# --------------------------------------------------------------------------- #
# URL validation
# --------------------------------------------------------------------------- #

def test_validate_pooled_endpoint():
    facts = validate_connection_url(POOLED_URL)
    assert facts.pooled is True
    assert facts.host_format == "PASS"
    assert facts.port == 5432
    assert facts.port_source == "EXPLICIT"
    assert facts.port_check == "PASS"
    assert facts.ssl_configured is True
    assert facts.ssl_mode == "require"
    assert facts.database_present is True


def test_validate_direct_endpoint_defaults_port():
    facts = validate_connection_url(DIRECT_URL)
    assert facts.pooled is False
    assert facts.port == 5432
    assert facts.port_source == "DEFAULT"
    assert facts.ssl_mode == "require"


def test_validate_missing_password():
    with pytest.raises(UrlValidationError) as error:
        validate_connection_url(
            "postgresql://fakeuser@ep-test-123.us-east-2.aws.neon.tech:5432/neondb"
        )
    assert error.value.code == "URL_MISSING_PASSWORD"


def test_validate_missing_database():
    with pytest.raises(UrlValidationError) as error:
        validate_connection_url("postgresql://fakeuser:fakepass@127.0.0.1:5432")
    assert error.value.code == "URL_MISSING_DATABASE"


def test_validate_wrong_scheme():
    with pytest.raises(UrlValidationError) as error:
        validate_connection_url("mysql://fakeuser:fakepass@127.0.0.1:3306/neondb")
    assert error.value.code == "BLOCKED_NOT_POSTGRESQL"


def test_validate_non_neon_host_is_warning_not_failure():
    facts = validate_connection_url("postgresql://fakeuser:fakepass@db.example.com:5432/neondb")
    assert facts.host_format == "WARN"


def test_validate_multiline_input_rejected():
    with pytest.raises(UrlValidationError) as error:
        validate_connection_url(DIRECT_URL + "\npostgresql://u:p@h/db")
    assert error.value.code == "BLOCKED_MULTILINE_INPUT"


def test_validate_non_standard_port_warns_without_revealing_it():
    facts = validate_connection_url(
        "postgresql://fakeuser:fakepass@ep-test-123.us-east-2.aws.neon.tech:6543/neondb"
    )
    assert facts.port_check == "WARN_NON_STANDARD"
    assert facts.port == 6543


# --------------------------------------------------------------------------- #
# Redaction
# --------------------------------------------------------------------------- #

def test_redact_removes_url_credentials_host_and_quoted_variants():
    password = "fake-pass!9"
    url = (
        f"postgresql://fakeuser:{password}"
        "@ep-test-123.us-east-2.aws.neon.tech:5432/neondb"
    )
    message = (
        f"failed to connect {url} password={password} "
        "host=ep-test-123.us-east-2.aws.neon.tech user=fakeuser "
        f"quoted={quote(password, safe='')} plus={quote_plus(password, safe='')}"
    )
    cleaned = redact(message, url)
    for secret in (
        url,
        password,
        "fakeuser",
        "ep-test-123.us-east-2.aws.neon.tech",
        quote(password, safe=""),
        quote_plus(password, safe=""),
    ):
        assert secret not in cleaned
    assert "<redacted>" in cleaned


# --------------------------------------------------------------------------- #
# Driver translation
# --------------------------------------------------------------------------- #

def test_translation_drops_libpq_params_and_builds_ssl_context():
    config = build_driver_config(validate_connection_url(POOLED_URL))
    assert config.url.drivername == "postgresql+asyncpg"
    assert "sslmode" not in config.url.query
    assert "channel_binding" not in config.url.query
    assert set(config.dropped_params) == {"sslmode", "channel_binding"}
    assert isinstance(config.sqlalchemy_connect_args["ssl"], ssl.SSLContext)
    assert config.ssl_context_required is True
    assert config.url.query.get("prepared_statement_cache_size") == "0"
    assert config.asyncpg_kwargs["statement_cache_size"] == 0


def test_translation_direct_endpoint_keeps_prepared_statement_cache():
    config = build_driver_config(validate_connection_url(DIRECT_URL))
    assert config.prepared_cache_disabled is False
    assert "prepared_statement_cache_size" not in config.url.query
    assert "statement_cache_size" not in config.asyncpg_kwargs


# --------------------------------------------------------------------------- #
# SQL allowlist
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "  select table_name from information_schema.tables",
        "-- leading comment\nSELECT 1",
        "/* block */ SHOW transaction_read_only",
        "SELECT 1;",
    ],
)
def test_sql_allowlist_accepts_read_only(sql):
    assert assert_read_only_sql(sql) == sql


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO t VALUES (1)",
        "UPDATE t SET a = 1",
        "DELETE FROM t",
        "DROP TABLE t",
        "ALTER TABLE t ADD COLUMN c integer",
        "CREATE TABLE t (id integer)",
        "TRUNCATE t",
        "  -- comment\nDELETE FROM t",
        "/* comment */ insert into t values (1)",
        "SET TRANSACTION READ ONLY",
        "SELECT 1; DROP TABLE t",
        "SeLeCt * FROM t FOR UPDATE",
    ],
)
def test_sql_allowlist_rejects_writes(sql):
    with pytest.raises(SqlNotAllowed):
        assert_read_only_sql(sql)


# --------------------------------------------------------------------------- #
# Input selection
# --------------------------------------------------------------------------- #

def test_zero_methods_rejected_without_tty():
    method, _, error = neon_probe.resolve_input_method([], False)
    assert method is None
    assert error == "BLOCKED_AMBIGUOUS_INPUT"


def test_interactive_allowed_with_tty():
    method, _, error = neon_probe.resolve_input_method([], True)
    assert method == "interactive"
    assert error is None


def test_multiple_methods_rejected():
    method, _, error = neon_probe.resolve_input_method(
        [("env", "A"), ("stdin", None)], True
    )
    assert method is None
    assert error == "BLOCKED_AMBIGUOUS_INPUT"


def test_single_method_accepted():
    method, variable, error = neon_probe.resolve_input_method([("env", "A")], False)
    assert (method, variable, error) == ("env", "A", None)


def test_from_env_deletes_variable(monkeypatch):
    monkeypatch.setenv("NEON_PROBE_TEST_URL", DIRECT_URL)
    url, marker = neon_probe.read_url_from_env("NEON_PROBE_TEST_URL")
    assert marker == "PASS"
    assert url == DIRECT_URL
    assert "NEON_PROBE_TEST_URL" not in os.environ


def test_from_env_missing_and_empty(monkeypatch):
    monkeypatch.delenv("NEON_PROBE_MISSING", raising=False)
    assert neon_probe.read_url_from_env("NEON_PROBE_MISSING") == (
        "",
        "BLOCKED_ENV_MISSING",
    )
    monkeypatch.setenv("NEON_PROBE_EMPTY", "   ")
    assert neon_probe.read_url_from_env("NEON_PROBE_EMPTY") == ("", "BLOCKED_ENV_EMPTY")


# --------------------------------------------------------------------------- #
# Probe subprocess output
# --------------------------------------------------------------------------- #

def test_probe_output_never_contains_credentials_or_addresses():
    result = _run_probe(
        ["--from-env", "NEON_PROBE_TEST_URL", "--purpose", "runtime", "--skip-inspection"],
        env_extra={"NEON_PROBE_TEST_URL": LOOPBACK_URL},
    )
    combined = result.stdout + result.stderr
    assert "URL_VALIDATION=PASS" in combined
    assert "HOST_FORMAT=WARN" in combined
    assert "POOLED=false" in combined
    assert "PORT_CHECK=WARN_NON_STANDARD" in combined
    assert "TCP=FAIL" in combined
    assert "FAILURE_CLASS=TCP_REFUSED" in combined
    assert "ASYNCPG_SELECT_1=NOT_STARTED" in combined
    assert result.returncode == 1
    for secret in ("fakeuser", "fakepass-loop", "127.0.0.1"):
        assert secret not in combined


def test_two_input_methods_are_rejected_by_cli():
    result = _run_probe(["--from-env", "NEON_PROBE_TEST_URL", "--stdin", "--purpose", "runtime"])
    assert result.returncode == 2
    assert "BLOCKED_AMBIGUOUS_INPUT" in result.stdout


def test_no_method_without_tty_is_rejected_by_cli():
    result = _run_probe(["--purpose", "runtime"])
    assert result.returncode == 2
    assert "BLOCKED_AMBIGUOUS_INPUT" in result.stdout


def test_missing_purpose_is_rejected():
    result = _run_probe(["--from-env", "NEON_PROBE_TEST_URL"])
    assert result.returncode == 2
    assert "BLOCKED_MISSING_PURPOSE" in result.stdout


# --------------------------------------------------------------------------- #
# Expected-table derivation (Stage 4 groundwork)
# --------------------------------------------------------------------------- #

def test_expected_tables_from_real_revision_match_orm():
    paths = discover_revision_paths(ROOT / "migrations" / "versions")
    expected = expected_tables(paths)
    assert expected_head_revision(paths) == "027fcf80b4b6"
    assert len(expected) == 15
    comparison = compare_tables(expected, orm_table_names())
    assert comparison.expected_count == 15
    assert comparison.missing == frozenset(), sorted(comparison.missing)
    # Known drift: the ORM declares a table that no revision creates.
    assert comparison.unexpected == frozenset({"activities"})


def test_expected_tables_apply_upgrade_operations_in_order(tmp_path):
    first = tmp_path / "a_rev.py"
    first.write_text(
        "revision = 'a1'\ndown_revision = None\n"
        "from alembic import op\n\n"
        "def upgrade():\n"
        "    op.create_table('alpha')\n"
        "    op.create_table('beta')\n\n"
        "def downgrade():\n"
        "    op.drop_table('alpha')\n",
        encoding="utf-8",
    )
    second = tmp_path / "b_rev.py"
    second.write_text(
        "revision = 'b2'\ndown_revision = 'a1'\n"
        "from alembic import op\n\n"
        "def upgrade():\n"
        "    op.drop_table('alpha')\n"
        "    op.rename_table('beta', 'gamma')\n\n"
        "def downgrade():\n"
        "    pass\n",
        encoding="utf-8",
    )
    assert expected_tables([second, first]) == {"gamma"}
    assert expected_head_revision([first, second]) == "b2"


# --------------------------------------------------------------------------- #
# Test isolation (A3)
# --------------------------------------------------------------------------- #

def test_conftest_forces_sqlite_despite_fake_postgres_environment(tmp_path):
    probe_test = tmp_path / "test_resolved_url.py"
    probe_test.write_text(
        "from backend.app.config import get_settings\n\n"
        "def test_resolved_url_is_sqlite():\n"
        "    assert get_settings().database_url.startswith('sqlite')\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    fake = (
        "postgresql+asyncpg://fakeuser:fakepass"
        "@ep-test-123.us-east-2.aws.neon.tech:5432/neondb"
    )
    environment["DATABASE_URL"] = fake
    environment["MIGRATION_DATABASE_URL"] = fake
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(probe_test),
            "-q",
            "-p",
            "no:warnings",
            "-p",
            "tests.conftest",
        ],
        cwd=str(ROOT),
        env=environment,
        capture_output=True,
        text=True,
        timeout=240,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in (result.stdout + result.stderr)


def test_conftest_assigns_database_url_unconditionally():
    text = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert 'os.environ["DATABASE_URL"] = TEST_DATABASE_URL' in text
    assert 'setdefault("DATABASE_URL"' not in text
    assert 'os.environ["MIGRATION_DATABASE_URL"] = TEST_DATABASE_URL' in text
