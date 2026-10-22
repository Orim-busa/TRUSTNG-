# TrustNG

Africa-focused fintech risk intelligence and transaction security API.

TrustNG provides transaction risk assessment, idempotency protections,
and investigation support for uncertain transaction outcomes.

The authenticated developer transaction-check endpoint is a risk-assessment
workflow only. It does not authorize or execute payments. A separate sandbox
workflow can simulate provider outcomes without moving real funds.

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
- The developer transaction-check endpoint does not invoke payment execution.
- The separate transaction executor is simulation-only; it does not move
  real funds.
- The sandbox provider workflow is isolated from the public risk-assessment
  endpoint and simulates outcomes without contacting a real payment provider.
- Database-backed reservations and idempotency checks help prevent duplicate
  submissions; uncertain outcomes require reconciliation before any retry.
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

## Account Trust (Sandbox)

TrustNG provides an advisory account-trust assessment workflow with sandbox
phone-verification support. These endpoints do not verify ownership of a bank
account and do not authorize or execute financial transfers.

### Authentication

All Account Trust endpoints require the `X-API-Key` request header. Keep your
API key private; never commit it to source control or include it in public
examples.

Set the API base URL in your shell:

    export TRUSTNG_BASE_URL='https://trustng-api.onrender.com'

Read your API key without displaying it:

    read -rsp 'Enter your TrustNG API key: ' TRUSTNG_API_KEY
    echo
    export TRUSTNG_API_KEY

### Available endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | `/v1/account-trust/otp/start` | Starts a sandbox phone-verification session. |
| POST | `/v1/account-trust/otp/verify` | Checks a sandbox verification code. |
| POST | `/v1/account-trust/check` | Returns an advisory account-trust assessment. |

For the exact request fields and response schemas, consult the API
documentation at `/docs` or the OpenAPI schema at `/openapi.json` on the
configured API host.

### Sandbox request examples

These examples use synthetic test data. Keep your API key private. The
responses may contain generated sandbox values; use the actual values returned
by your running service rather than the placeholders below.

Start a sandbox OTP session:

    curl -sS -X POST "$TRUSTNG_BASE_URL/v1/account-trust/otp/start" \
      -H "X-API-Key: $TRUSTNG_API_KEY" \
      -H "Content-Type: application/json" \
      -d '{"phone_number":"+2348000000000"}'

Read the returned `verification_id` and sandbox code from the response. No SMS
is sent in sandbox mode.

Verify the session, replacing both placeholders with the returned values:

    curl -sS -X POST "$TRUSTNG_BASE_URL/v1/account-trust/otp/verify" \
      -H "X-API-Key: $TRUSTNG_API_KEY" \
      -H "Content-Type: application/json" \
      -d '{"verification_id":"PASTE_VERIFICATION_ID","code":"PASTE_SIX_DIGIT_CODE"}'

Request an account-trust assessment using the same test phone number and
verification ID:

    curl -sS -X POST "$TRUSTNG_BASE_URL/v1/account-trust/check" \
      -H "X-API-Key: $TRUSTNG_API_KEY" \
      -H "Content-Type: application/json" \
      -d '{"country":"NG","account_identifier":"1234567890","phone_number":"+2348000000000","verification_id":"PASTE_VERIFICATION_ID"}'

Request field requirements:

- OTP start: `phone_number` is required (7–20 characters).
- OTP verify: `verification_id` and a six-digit `code` are required.
- Account trust check: `account_identifier` and `phone_number` are required;
  `country` defaults to `NG` and must be a two-character code when supplied.
  `verification_id` is optional in the request schema. Supply it when using the
  OTP workflow.
- Use synthetic data for sandbox testing. A successful response is not proof
  of real-world identity, phone ownership, or bank-account ownership.

### Sandbox workflow

1. Start verification using the documented request schema for the OTP start
   endpoint.
2. In sandbox mode, use the returned sandbox code to test verification.
3. Submit the verification details to the OTP verification endpoint.
4. Submit the account-trust assessment request using the documented schema.
5. Handle the returned assessment as advisory information requiring appropriate
   human review.

A successfully verified sandbox phone number is not proof of bank-account
ownership or identity. A verification session is single-use; consumed,
expired, or invalid sessions must not be reused.

### Current limitations and safety

- Sandbox OTP does not send a real SMS.
- Sandbox verification is not real-world phone, identity, or bank-account
  verification.
- Verification sessions are stored in process memory. They can be lost when
  the service restarts and are not shared between multiple service instances.
- The account-trust result is advisory and may require human review.
- The provider is not connected for real account verification.
- Account-trust assessment does not authorize or execute a transfer.
- Do not use sandbox responses as evidence that a real account is trustworthy.
- Production use requires suitable persistent session storage, rate limiting,
  monitoring, real verification-provider integration, and security review.
