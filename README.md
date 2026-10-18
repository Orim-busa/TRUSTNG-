# TrustNG

Africa-focused fintech risk intelligence and transaction security API.

TrustNG provides transaction risk assessment, policy-controlled execution
gates, idempotency protections, and investigation support for uncertain
transaction execution outcomes.

## Current status

TrustNG is a developer API prototype deployed at:

- API and landing page: https://trustng-api.onrender.com/
- Health check: https://trustng-api.onrender.com/v1/health
- Dashboard: https://trustng-api.onrender.com/dashboard

The health endpoint reports API availability and database connectivity.
It does not certify that every API operation or external payment provider
is operational.

## Important execution limitation

**Transaction execution is currently simulated. It does not move real funds.**

TrustNG does not currently act as a live payment processor through this
execution path. Do not use a successful simulated execution as evidence
that a bank transfer, wallet transfer, card payment, or other real payment
has settled.

Before integrating real payments, a production implementation needs a
payment-provider integration, verified provider-side transaction status,
secure credentials, provider idempotency support where available, webhook
verification, reconciliation procedures, monitoring, and appropriate
operational and regulatory review.

## Core safety principles

- Risk intelligence is advisory; it does not independently authorize
  financial transactions.
- Execution must pass the configured Execution Gate.
- Transaction identifiers and database-backed execution claims help
  prevent duplicate processing.
- An uncertain execution outcome must be investigated before retrying.
- A PENDING execution record is not proof of payment success or failure.
- Never expose API keys, database credentials, or other secrets in source
  control, logs, screenshots, or public issue reports.

## Requirements

- Python compatible with the project environment
- Git
- PostgreSQL if testing database-backed functionality
- The project dependencies installed in a virtual environment

## Run locally

From the project directory:

```bash
cd ~/trustng

python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Configure environment variables in a local `.env` file. Do not commit
this file.

Required configuration for database-backed operation:

- `DATABASE_URL`: PostgreSQL connection string.
- `TRUSTNG_API_KEY`: secret used to authenticate protected API requests.

Use the database provider's current connection details. Keep credentials
private and ensure `.env` is excluded by `.gitignore`.

Start the development server:

```bash
.venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Check local health:

```bash
curl -i http://127.0.0.1:8000/v1/health
```

For the deployed service, use the public URLs listed above.

## Authentication

Protected API routes require the `X-API-Key` request header.

Example using an environment variable already configured in your shell:

```bash
curl -i \
  -H "X-API-Key: ${TRUSTNG_API_KEY}" \
  https://trustng-api.onrender.com/v1/reconciliation/pending
```

Do not place a real API key directly in a command that you intend to
publish or share. An absent or invalid key should be rejected.

## Transaction risk check

The transaction-check endpoint is:

`POST /v1/transactions/check`

It requires a valid `X-API-Key` header and a JSON transaction body.
The current transaction model uses these fields:

| Field | Meaning |
| --- | --- |
| `transaction_id` | Unique identifier for the transaction |
| `sender` | Sender identifier |
| `receiver` | Receiver or beneficiary identifier |
| `asset` | Asset or currency, such as `NGN` |
| `amount` | Transaction amount |
| `channel` | Originating channel |
| `country` | Transaction country code |
| `device_id` | Optional device identifier |

Example request using test data only:

```bash
curl -i -X POST \
  "https://trustng-api.onrender.com/v1/transactions/check" \
  -H "X-API-Key: ${TRUSTNG_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "trustng-doc-test-001",
    "sender": "test-sender",
    "receiver": "test-beneficiary",
    "asset": "NGN",
    "amount": 1500,
    "channel": "api_test",
    "country": "NG",
    "device_id": "test-device-001"
  }'
```

This example illustrates the request shape; it is not a guarantee of
approval or a particular response. Use unique test identifiers and
inspect the actual response returned by the deployed API.

## Pending execution reconciliation

The protected endpoint is:

`GET /v1/reconciliation/pending`

It lists aged PENDING execution records that may require investigation.
The endpoint supports these query parameters:

- `older_than_minutes`: age threshold in minutes, from 0 to 10080.
- `limit`: maximum number of records, from 1 to 200.

Example:

```bash
curl -i \
  -H "X-API-Key: ${TRUSTNG_API_KEY}" \
  "https://trustng-api.onrender.com/v1/reconciliation/pending?older_than_minutes=5&limit=50"
```

A returned record is an investigation candidate, not a conclusion about
whether a payment succeeded or failed. Check the authoritative payment
provider's status before resolving an uncertain outcome or retrying it.
An empty result means no records matched that query; it does not prove
that all payments have settled.

## Health and tests

Deployed health check:

```bash
curl -i https://trustng-api.onrender.com/v1/health
```

Run the test suite locally:

```bash
cd ~/trustng
.venv/bin/python -m pytest -q
```

Tests validate implemented behavior; they do not by themselves establish
production readiness or certify a real payment integration.

## Deployment notes

The deployed service uses Render, and the application database is
configured through environment variables. Keep production credentials
in the hosting provider's secret environment settings. Verify health,
database connectivity, authentication, logs, and relevant tests after
each deployment.

## Current limitations and next steps

Before inviting partners to rely on TrustNG in production:

1. Confirm the API contract and error responses for every public route.
2. Complete security and authorization review.
3. Integrate a payment provider in a controlled test environment.
4. Verify provider status and webhook authenticity.
5. Test duplicate requests, timeouts, process crashes, and recovery.
6. Define reconciliation ownership and incident procedures.
7. Add appropriate monitoring, rate limiting, and audit controls.
8. Complete applicable legal, regulatory, and partner reviews.

TrustNG's risk assessment and simulated execution features must not be
represented as proof of real payment authorization, execution, or settlement.
