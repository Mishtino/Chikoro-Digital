"""Refuse to run database tooling unless DATABASE_URL targets local Chikoro PostgreSQL.

Usage:
  DATABASE_URL=postgresql://... python scripts/local_db_guard.py -- alembic upgrade head

This guard is intentionally strict. It does not execute SQL itself and does not
make a Supabase-specific migration compatible with vanilla PostgreSQL.
"""
from __future__ import annotations

import os
import subprocess
import sys
from urllib.parse import urlparse


ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
ALLOWED_PORT = 55432
ALLOWED_DATABASE = "chikoro_local"
ALLOWED_SCHEMES = {"postgres", "postgresql"}


def validate_database_url(database_url: str) -> tuple[bool, str]:
    if not database_url:
        return False, "DATABASE_URL is not set."

    # urllib.parse strips ASCII tabs/newlines and some leading controls. Never
    # validate a normalized URL that differs from the supplied connection URI.
    if any(ord(char) < 33 or ord(char) == 127 for char in database_url):
        return False, "DATABASE_URL contains whitespace or control characters."

    try:
        parsed = urlparse(database_url)
        port = parsed.port
    except ValueError:
        return False, "DATABASE_URL is malformed."

    database = parsed.path
    # Require the exact canonical URI path; libpq and URL parsers can differ
    # when interpreting repeated slashes or percent-encoded path characters.
    # libpq accepts connection parameters in the URI query string. Reject them
    # so a validated loopback authority cannot be paired with an overriding
    # host/hostaddr/service parameter when the child process opens the URL.
    if parsed.query or parsed.fragment:
        return False, "Query parameters and fragments are not allowed in DATABASE_URL."
    if parsed.scheme not in ALLOWED_SCHEMES:
        return False, "Only PostgreSQL URLs are accepted."
    if parsed.hostname not in ALLOWED_HOSTS:
        return False, "Refusing non-local database host."
    if port != ALLOWED_PORT:
        return False, f"Refusing database port; expected {ALLOWED_PORT}."
    if database != f"/{ALLOWED_DATABASE}":
        return False, f"Refusing database name; expected {ALLOWED_DATABASE}."
    return True, "Local Chikoro PostgreSQL target verified."


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "--":
        args.pop(0)
    if not args:
        print("Usage: python scripts/local_db_guard.py -- <database command>", file=sys.stderr)
        return 2

    allowed, message = validate_database_url(os.environ.get("DATABASE_URL", ""))
    if not allowed:
        print(f"BLOCKED: {message}", file=sys.stderr)
        return 2

    print(f"OK: {message}")
    return subprocess.run(args, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
