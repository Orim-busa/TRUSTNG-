# TrustNG Technical Architecture

**Document type:** Technical Architecture
**Version:** 1.0
**Product:** TrustNG
**Status:** Current-state architecture documentation
**Deployment model:** Python API hosted on Render
**Last reviewed:** 6 November 2026

---

## 1. Executive Summary

TrustNG is an Africa-focused financial technology risk-intelligence and transaction-security API.

Its purpose is to provide risk assessment, fraud-risk indicators, transaction-policy decisions, recipient contact verification and supporting investigation capabilities.

TrustNG is designed as a risk-intelligence layer. It does not operate as a bank, hold customer funds, initiate real payments, execute bank transfers or independently authorize financial transactions.

The current implementation uses a Python application built with FastAPI, rule-based risk engines, PostgreSQL persistence for selected records, and simulated sandbox provider operations.

The architecture separates risk assessment, policy decisions, authorization controls and simulated execution safeguards.

**Important:** The current implementation is a development and sandbox-oriented system. Its capabilities should not be interpreted as proof of production readiness, regulatory approval or live financial-institution integration.

## 2. System Architecture Overview

The application consists of the following major layers:

1. API and request-handling layer.
2. Transaction validation and idempotency layer.
3. Risk intelligence and behavioural analysis layer.
4. Trust assessment and AI advisory layer.
5. Policy decision layer.
6. Database and persistence layer.
7. Recipient verification and account-trust layer.
8. Fraud investigation and audit layer.
9. Sandbox provider and execution-safety layer.
10. Deployment and operational infrastructure.

### 2.1 High-level architecture

```text
Developer / Integrating Application
                |
                v
        TrustNG FastAPI
                |
                v
       API Authentication
                |
                v
     Request Validation
                |
                v
       Idempotency Control
                |
                v
       Transaction Analysis
                |
       +--------+---------+
       |        |         |
       v        v         v
    Risk     Behaviour   Trust
   Engine     Analysis  Assessment
       |        |         |
       +--------+---------+
                |
                v
       AI Advisory Assessment
                |
                v
        Policy Decision Engine
                |
                v
       Risk Assessment Response
                |
       +--------+----------+
       |                   |
       v                   v
  Fraud Case          Persistence
  Creation            and Recovery
```

The diagram represents the principal risk-assessment flow. Recipient verification, account-trust checks, investigation functions and sandbox provider operations are supporting workflows rather than mandatory stages in every transaction evaluation.

## 3. Technology Stack

| Component | Technology | Responsibility |
|---|---|---|
| Programming language | Python | Application logic |
| API framework | FastAPI | HTTP endpoints and request handling |
| ASGI server | Uvicorn | Application serving |
| Data validation | Pydantic | Request and model validation |
| Database | PostgreSQL | Persistent transaction and verification records |
| Database driver | Psycopg | PostgreSQL connectivity |
| Environment configuration | python-dotenv | Local environment-variable loading |
| Country information | pycountry | Country-code support |
| Hosting | Render | Web-service deployment |

### 3.1 Python dependencies

The current dependency manifest specifies:

- `fastapi==0.141.1`
- `uvicorn==0.53.0`
- `pydantic==2.13.5`
- `psycopg[binary]==3.3.6`
- `python-dotenv==1.2.4`
- `pycountry>=24.6.1`

## 4. API Architecture

The application exposes HTTP endpoints through FastAPI.

The API includes transaction-risk assessment, recipient verification, account-trust checks, fraud investigation, reconciliation, dashboard and supporting research functionality.

### 4.1 Principal API endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/v1/health` | GET | Service and database connectivity status |
| `/v1/transactions/check` | POST | Authenticated transaction-risk assessment |
| `/evaluate` | POST | Core risk evaluation |
| `/v1/transactions/check-by-email` | POST | Resolve verified recipient contact and assess risk |
| `/v1/recipients/register` | POST | Register an email recipient |
| `/v1/recipients/verification/start` | POST | Start email and assigned-phone verification |
| `/v1/recipients/verification/confirm` | POST | Confirm both contact verification codes |
| `/v1/recipients/lookup` | POST | Look up a registered recipient |
| `/v1/payment-requests/by-email` | POST | Create a persistent sandbox request |
| `/v1/account-trust/otp/start` | POST | Start sandbox account-trust OTP verification |
| `/v1/account-trust/otp/verify` | POST | Verify a sandbox OTP |
| `/v1/account-trust/check` | POST | Assess account-trust information |
| `/v1/reconciliation/pending` | GET | Retrieve pending reconciliation records |
| `/fraud-cases` | GET | List fraud investigation cases |
| `/fraud-cases/{case_id}` | GET | Retrieve a fraud case |
| `/audit/integrity` | GET | Check stored audit-event fingerprints |

Additional dashboard, terminal, research and fraud-investigation routes are implemented in `main.py`.

### 4.2 API authentication

The application uses an API-key mechanism based on the `X-API-Key` HTTP header.

The configured key is supplied through the `TRUSTNG_API_KEY` environment variable.

The application uses constant-time comparison through `secrets.compare_digest` for API-key comparisons.

A global middleware protects internal routes. Public exceptions include the health endpoint, dashboard and documentation paths, along with other explicitly configured public paths.

The API documentation also defines API-key security for protected operations.

The public health endpoint does not expose the API key.

## 5. Transaction Risk Assessment Architecture

The principal risk-assessment workflow is implemented through `main.py`
 and supporting modules.

The risk-assessment workflow evaluates transaction information and supporting risk indicators before producing a policy recommendation.

The assessment considers several categories of information:

- Transaction amount and asset.
- Transaction channel and country.
- Device information, where available.
- Sender and beneficiary transaction history.
- Transaction velocity.
- Beneficiary profile information.
- Behavioural anomalies.
- Relationship and trust-graph indicators.

The risk engine produces rule-based risk signals. These signals are inputs to the wider assessment and policy process.

The system does not establish that a transaction is fraudulent merely because a risk signal is present. Signals are indicators that may require further review.

## 6. AI Advisory Architecture

The AI component is implemented in `ai_risk_engine.py`.

It is named `TrustNG-AI-Risk-Intelligence`, version 1.0.

The component provides an advisory risk assessment using rule-based scoring and available risk information.

Its output may include:

- An advisory score.
- A risk classification.
- Recommended review or monitoring actions.
- An indication that the confidence level is not calibrated.

The AI component does not authorize transactions, execute payments, release funds, or override the policy engine.

Its output is advisory only. The TrustNG policy engine remains responsible for the final policy decision.

The current implementation is not a statistically trained or independently validated fraud-prediction model. Its scores should not be presented as calibrated probabilities of fraud.

## 7. Policy Decision Architecture

The policy engine is implemented in `policy_engine.py`.

The current policy identifier is `NG-TRANSFER-001`, version `1.0`.

The policy evaluates available risk signals and the trust assessment to produce a decision.

Possible outcomes include:

- `ALLOW`
- `REVIEW`
- `RESTRICT`

The policy may also return a risk level, recommended action, reasons, and applicable restrictions.

A `RESTRICT` result is a TrustNG policy recommendation. It does not mean that TrustNG has restricted a bank account or executed a payment-control instruction.

The policy result does not constitute payment authorization.
## 8. Idempotency and Transaction Safety

TrustNG implements transaction reservation and idempotency controls through `idempotency.py`.

The system uses a transaction fingerprint to identify whether a transaction request is a replay of an earlier request or an attempt to reuse a transaction ID with different transaction details.

The reservation process can return outcomes such as:

- `REPLAY`: a matching transaction has already been recorded.
- `ID_REUSE`: the transaction ID is being reused with different details.
- `PROCESSING`: an earlier request is still being processed.
- `INVALID`: the transaction request cannot be reserved.

Where a database is configured, database-backed reservation and persistence are used. Local in-memory state is also available for non-database operation.

The idempotency controls are intended to reduce duplicate processing. They do not independently authorize or execute payments.

## 9. Database Architecture

Database operations are implemented in `database.py` using PostgreSQL and the Psycopg driver.

The database connection is configured through the `DATABASE_URL` environment variable.

Database initialization creates the application's required tables, indexes and schema structures.

The current database design includes storage for:

- Processed transaction records.
- Transaction execution records.
- Consumed authorization records.
- Sandbox provider operations.
- Recipient email aliases.
- Recipient email verification challenges.
- Email payment requests.

Database-backed records support transaction reservation, replay protection, status tracking and recovery workflows.

Database availability is required for certain features, including database-backed recipient verification and email payment requests.

The database does not act as a bank ledger or hold customer funds.

## 10. Recipient Contact Verification

Recipient contact verification is implemented through the recipient directory and related API routes.

The current design separates email ownership, phone ownership, legal identity verification and payment authorization.

The recipient verification workflow uses two separate one-time passwords:

- One sent to the registered email address.
- One sent to the assigned phone number.

Both verification steps must succeed before the contact status becomes `FULLY_VERIFIED`.

Verification codes are stored as protected hashes, with an expiry period and attempt limits.

The trusted phone number is assigned during recipient registration. The recipient cannot replace that number by supplying a different phone number during verification.

Successful email and phone verification establishes contact ownership only. It does not establish legal identity, authorize a payment or prove ownership of a bank account.

The current implementation must be treated according to its configured delivery mode. Sandbox delivery is not production-grade identity verification.
## 11. Account Trust Assessment

Account trust assessment is implemented in `account_trust_check.py`.

The current account-trust workflow uses a sandbox one-time-password mechanism with expiry and attempt limits.

The assessment can use available account and verification information to produce a trust result.

This mechanism is separate from the recipient email and phone verification workflow.

A successful sandbox OTP does not prove ownership of a real bank account, establish legal identity or authorize a payment.

The current OTP session and rate-limit state is maintained in application memory. It is not a distributed production verification service.

## 12. Fraud Investigation and Audit Architecture

Fraud investigation functionality is implemented through `fraud_cases.py`.

The system can create fraud cases from qualifying risk-assessment results and retain supporting information such as:

- Transaction details.
- Risk decisions and classifications.
- Risk signals.
- Behavioural anomaly indicators.
- Trust assessment information.
- Investigation notes and actions.

Fraud case statuses include `OPEN`, `UNDER_REVIEW`, `RESOLVED` and `DISMISSED`.

The current fraud case store is in application memory. It is not yet a persistent, database-backed case management system.

Audit event storage is implemented in `audit_store.py`, using a local JSON file.

Audit integrity checks use SHA-256 fingerprints to detect certain changes to recorded event content.

The current audit mechanism is not a tamper-proof or independently secured audit service. It does not provide immutable external storage or independently authenticated investigator identities.

## 13. Sandbox Provider and Execution Safety

Sandbox execution components include:

- `execution_gate.py`
- `transaction_executor.py`
- `provider_adapter.py`
- `sandbox_provider_service.py`

These modules provide safeguards for simulated execution workflows, including authorization checks, transaction identity validation, duplicate-execution protection and reconciliation handling.

The provider adapter is sandbox-only and does not connect to a live banking or payment network.

Simulated execution does not move real funds.

Uncertain outcomes are handled through reconciliation states rather than assuming that execution succeeded.

A `PENDING` provider operation is inspected for its existing status. The system does not blindly submit the same operation again.

These components demonstrate sandbox execution-safety controls. They do not establish production payment-processing capability or approval to connect to financial institutions.
## 14. Deployment Architecture

TrustNG is configured for deployment as a Python web service on Render.

The application uses Uvicorn as its ASGI server and FastAPI as its web framework.

The deployment configuration is defined in `render.yaml`.

The service is configured to use environment variables for sensitive configuration, including:

- `DATABASE_URL`
- `TRUSTNG_API_KEY`

These values must be configured securely in the hosting environment. Secrets must not be committed to source control or included in public documentation.

The current deployment configuration does not, by itself, demonstrate production availability, scalability or disaster recovery capability.

## 15. Health Monitoring

The application provides a health endpoint at `/v1/health`.

The endpoint reports the application status and database connection status.

A successful health response confirms only the checks implemented by that endpoint. It does not prove that every API route, background operation or external delivery service is functioning correctly.

Production monitoring should include service availability, database connectivity, error rates, latency, security events and operational alerts.

## 16. Security Architecture and Controls

The current implementation includes several security-related controls:

- API-key protection for internal routes.
- Constant-time API-key comparison.
- Environment-based configuration for sensitive values.
- Database-backed transaction reservation and idempotency.
- OTP expiry and attempt limits.
- Hashed recipient verification codes.
- Transaction identity and replay checks.
- Authorization expiry and reuse checks in the execution-gate module.
- Reconciliation handling for uncertain sandbox operations.

These controls reduce specific risks but do not constitute a complete production security programme.

Further security work is required, including independent security testing, production-grade secrets management, access-role design, monitoring, incident response procedures and review of deployment-level protections.

## 17. Current Architecture Limitations

The current implementation has important limitations that must be considered during testing and regulatory review.

1. The risk engine and AI advisory component use rule-based logic. Their predictive performance has not been independently validated.
2. The AI confidence level is not statistically calibrated.
3. Behavioural profiles and some relationship indicators are illustrative and partly maintained in application memory.
4. Fraud investigation cases are currently stored in application memory rather than a persistent case-management database.
5. Audit records use local file storage and do not provide immutable, independently secured evidence.
6. The account-trust OTP mechanism is sandbox-only and uses application-memory session state.
7. Sandbox provider operations do not connect to live payment networks.
8. Production-grade identity verification and financial-institution integrations have not been established by the current implementation.
9. Deployment-level security, resilience, backup and disaster recovery arrangements require further validation.

These limitations should be treated as open engineering and validation requirements, not as capabilities already delivered.

## 18. Production and Regulatory Readiness Considerations

Before any production deployment or regulated financial-sector integration, TrustNG will require further technical, operational and governance work.

Key areas include:

- Independent security assessment and penetration testing.
- Documented risk-model testing and validation.
- Production-grade identity and contact verification.
- Persistent and access-controlled fraud case management.
- Stronger audit integrity and retention controls.
- Operational monitoring and incident response.
- Database backup, restoration and disaster recovery testing.
- Defined access roles and administrative controls.
- Secure integration and testing with approved financial-sector partners.
- Legal and regulatory review of the intended service model.

TrustNG's current architecture is designed around advisory transaction-risk intelligence and fraud-prevention support.

TrustNG does not hold customer funds, initiate real payments, execute live transfers or independently authorize financial transactions.

The current sandbox implementation must not be represented as CBN approval, production certification or authorization to connect to live financial systems.

## 19. Conclusion

TrustNG provides a modular foundation for transaction-risk assessment, policy recommendations, recipient contact verification, fraud investigation support and sandbox execution-safety testing.

Its architecture separates risk assessment and policy recommendations from payment authorization and execution.

The current implementation provides a basis for continued engineering, controlled testing and regulatory engagement. Additional validation, security hardening, operational controls and approved integrations will be required before production use.
