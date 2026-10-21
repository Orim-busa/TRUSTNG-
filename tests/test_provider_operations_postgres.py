"""Opt-in integration tests requiring a dedicated PostgreSQL test database."""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from dotenv import dotenv_values

import database


@pytest.mark.parametrize("workers", [12])
def test_concurrent_provider_reservations_are_atomic(
    monkeypatch, workers
):
    if os.getenv("TRUSTNG_RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("Set TRUSTNG_RUN_POSTGRES_INTEGRATION=1 to opt in.")

    env_file = dotenv_values(Path.cwd() / ".env")
    test_url = (
        os.environ.get("TRUSTNG_TEST_DATABASE_URL")
        or env_file.get("TRUSTNG_TEST_DATABASE_URL")
    )
    if not test_url:
        pytest.skip("TRUSTNG_TEST_DATABASE_URL is not configured.")

    production_urls = {
        value
        for value in (
            os.environ.get("DATABASE_URL"),
            env_file.get("DATABASE_URL"),
        )
        if value
    }

    test_host = urlparse(test_url).hostname
    if not test_host:
        pytest.fail("Refusing to run: test database URL has no valid hostname.")

    for production_url in production_urls:
        production_host = urlparse(production_url).hostname
        if not production_host or test_host.lower() == production_host.lower():
            pytest.fail(
                "Refusing integration writes: test database hostname matches "
                "or cannot be distinguished from a configured production URL."
            )

    # All database helpers in this test use the explicitly configured test URL.
    monkeypatch.setenv("DATABASE_URL", test_url)

    # Require a pre-created test schema; never create application tables here.
    with database.get_database_connection() as connection:
        row = connection.execute(
            """
            SELECT to_regclass('public.provider_operations') AS table_name
            """
        ).fetchone()

    if not row or row["table_name"] is None:
        pytest.fail(
            "The dedicated test database must already contain "
            "public.provider_operations. Prepare its schema separately."
        )

    suffix = uuid4().hex
    key = f"postgres-concurrency-key-{suffix}"
    provider = "sandbox-concurrency-test"
    transaction_id = f"postgres-concurrency-tx-{suffix}"
    fingerprint = f"postgres-concurrency-fingerprint-{suffix}"

    def reserve(_):
        return database.reserve_or_inspect_provider_operation(
            key, provider, transaction_id, fingerprint
        )

    try:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(reserve, range(workers * 2)))

        decisions = [item["decision"] for item in results]

        assert decisions.count("RESERVED") == 1
        assert decisions.count("CHECK_PROVIDER_STATUS") == (
            workers * 2 - 1
        )
        assert all(
            item["operation"] is None
            for item in results
            if item["decision"] == "RESERVED"
        )

        with database.get_database_connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS row_count
                FROM provider_operations
                WHERE provider = %s AND transaction_id = %s
                """,
                (provider, transaction_id),
            ).fetchone()

        assert row["row_count"] == 1

    finally:
        # Remove only this test's uniquely identified row.
        with database.get_database_connection() as connection:
            connection.execute(
                """
                DELETE FROM provider_operations
                WHERE idempotency_key = %s
                  AND provider = %s
                  AND transaction_id = %s
                """,
                (key, provider, transaction_id),
            )
