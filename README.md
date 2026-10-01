# LedgerFlow

LedgerFlow is a payment reliability simulator designed to investigate what happens when payment requests are retried, duplicated, executed concurrently, interrupted by worker failures, or left with an uncertain processor outcome.

The project is not a real payment processor and does not move real money.

Its purpose is to model the reliability problems that appear at the boundary between an HTTP API, a database, background processing, and an unreliable external payment processor, then experimentally validate the mechanisms used to make those systems safer.

---

# Project Thesis

A payment request can fail in ways that are fundamentally ambiguous.

A client may send a payment request and never receive the response.

The server may have completed the payment before the response was lost.

The client then retries.

From the client's perspective:

```text
Did the payment fail?
Did the server process it?
Did the processor receive it?
Did the processor complete it?
Is it safe to retry?
````

A naive implementation may interpret the missing response as failure and create another payment.

That creates the possibility of duplicate side effects.

LedgerFlow investigates this class of failure by treating payment processing as a distributed reliability problem rather than simply a CRUD application.

The engineering approach is:

```text
Real failure mode
      ↓
Investigate
      ↓
Form hypothesis
      ↓
Design mechanism
      ↓
Implement
      ↓
Break the system
      ↓
Measure behavior
      ↓
Compare against invariants
      ↓
Redesign
      ↓
Re-test
```

---

# What LedgerFlow Investigates

The project focuses on several reliability problems.

## 1. Duplicate Requests

A client may retry the same logical payment request.

Without idempotency:

```text
Request 1 → Payment A
Request 2 → Payment B
```

With idempotency:

```text
Request 1 ─┐
           ├──→ Payment A
Request 2 ─┘
```

Both requests represent the same logical payment operation.

---

## 2. Concurrent Requests

Two identical requests can arrive almost at the same time.

A simple existence check is insufficient:

```text
Request A                 Request B

check key                 check key
key missing               key missing

create payment            create payment
```

Both requests can observe the database before either has committed its record.

LedgerFlow therefore uses database-enforced uniqueness together with transactional creation.

The database is part of the correctness mechanism.

---

## 3. Lost Responses

A payment can succeed while the client receives no usable response.

The client may therefore retry an operation that already succeeded.

LedgerFlow uses an idempotency key to associate multiple HTTP attempts with one logical payment.

---

## 4. Worker Crashes

A background worker can fail at different points:

```text
claim job
   ↓
update payment
   ↓
call processor
   ↓
processor completes
   ↓
record result
   ↓
complete job
```

A worker crash between these operations can leave the system in an uncertain state.

LedgerFlow models worker leases so that unfinished jobs can become recoverable.

---

## 5. Transient Failures

Some failures may be temporary.

Examples include:

* temporary processor failure;
* network interruption;
* infrastructure failure;
* temporary downstream unavailability.

These failures can be retried.

LedgerFlow uses bounded exponential backoff.

The current retry schedule is:

```text
Attempt 1 → 5 seconds
Attempt 2 → 10 seconds
Attempt 3 → 20 seconds
Maximum   → 60 seconds
```

Retries are bounded by a maximum number of job attempts.

---

## 6. Permanent Failures

Some failures should not be automatically retried.

Examples include permanent processor rejection or invalid business conditions.

LedgerFlow distinguishes transient failures from permanent failures.

```text
Transient failure
      ↓
Retry

Permanent failure
      ↓
Terminal failure
```

---

## 7. Unknown Processor Outcomes

The most important failure case is not necessarily a confirmed failure.

A processor call can return an unknown outcome.

For example:

```text
LedgerFlow → Processor
             ↓
             operation succeeds
             ↓
       network interruption
             ↓
LedgerFlow receives no result
```

The processor may have completed the operation even though LedgerFlow does not know that yet.

LedgerFlow therefore models:

```text
Payment
    PROCESSING
    SUCCEEDED
    FAILED

PaymentAttempt
    SUCCESS
    FAILED
    UNKNOWN
```

`UNKNOWN` belongs to the payment attempt, not the normal payment lifecycle.

This distinction allows the system to preserve uncertainty without incorrectly declaring the payment itself successful or failed.

---

# Core Design Principle

An important design decision in LedgerFlow is:

> A retry is not necessarily a new payment.

A retry can instead be another attempt to resolve the same logical payment.

The conceptual model is:

```text
Payment
│
├── Attempt 1
│      UNKNOWN
│      processor_operation_id = X
│
└── Attempt 2
       SUCCESS
       processor_operation_id = X
```

The payment can ultimately become:

```text
SUCCEEDED
```

without creating a second processor operation.

This is particularly important when recovering from uncertain outcomes.

---

# Architecture

LedgerFlow is organized around the following flow:

```text
                    ┌──────────────────┐
                    │      Client      │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │    Django API    │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │   Idempotency    │
                    │     Layer        │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │     Payment      │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │   PostgreSQL     │
                    │    Job Queue     │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Payment Worker   │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │    Processor     │
                    │    Simulator     │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Reconciliation   │
                    └──────────────────┘
```

The processor is deliberately simulated.

This makes it possible to deterministically reproduce:

```text
SUCCESS
TRANSIENT_FAILURE
PERMANENT_FAILURE
UNKNOWN
```

without interacting with a real payment network.

---

# Technology Stack

## Backend

* Python
* Django
* Django ORM
* PostgreSQL

## Application Server

* Gunicorn

## Static Files

* WhiteNoise

## Configuration

* python-dotenv
* Environment variables

## Database

* PostgreSQL 17

## Frontend

* Django templates
* HTML
* CSS
* JavaScript

The interface is intentionally designed as an operational engineering tool rather than a generic admin dashboard.

The visual system uses restrained typography, dense information hierarchy, state-aware interaction, and minimal motion.

---

# Repository Structure

```text
ledgerflow/
│
├── docs/
│   ├── README.md
│   ├── problem.md
│   ├── api-contract.md
│   ├── payment-lifecycle.md
│   ├── data-model.md
│   ├── concurrency.md
│   └── retry-and-reconciliation.md
│
├── experiments/
│   ├── concurrency/
│   │   ├── README.md
│   │   └── results.md
│   │
│   ├── worker-crash/
│   │   ├── README.md
│   │   └── results.md
│   │
│   ├── retry-reconciliation/
│   │   ├── README.md
│   │   └── results.md
│   │
│   └── production-deployment/
│       ├── README.md
│       └── results.md
│
├── src/
│   ├── api/
│   ├── config/
│   ├── payments/
│   ├── static/
│   ├── templates/
│   ├── db.sqlite3
│   └── manage.py
│
├── tests/
│
├── .gitignore
├── build.sh
├── docker-compose.yml
├── requirements.txt
├── render.yaml
└── README.md
```

The root README provides the project-level narrative.

The `docs/` directory contains detailed engineering design documentation.

The `experiments/` directory contains evidence from controlled reliability experiments.

---

# Core Data Model

LedgerFlow separates the logical payment from individual processing attempts.

## Payment

Represents the logical payment.

States:

```text
CREATED
PROCESSING
SUCCEEDED
FAILED
```

Important fields include:

```text
amount
currency
status
created_at
updated_at
```

---

## IdempotencyRecord

Associates an idempotency key with one payment.

Important fields:

```text
key
payment
request_fingerprint
created_at
```

The idempotency key is unique.

The request fingerprint prevents the same key from being reused with different request data.

---

## PaymentAttempt

Represents an attempt to process a payment through the processor.

States:

```text
SUCCESS
FAILED
UNKNOWN
```

Important fields include:

```text
payment
processor_operation_id
status
failure_type
error
created_at
completed_at
```

A payment can have multiple attempts.

---

## ProcessorOperation

Represents an operation inside the simulated external processor.

Important fields:

```text
operation_id
outcome
created_at
```

The operation ID is unique.

This allows the simulator to reproduce idempotent processor behavior and demonstrate recovery from uncertain outcomes.

---

## PaymentJob

Represents asynchronous work associated with a payment.

States:

```text
QUEUED
PROCESSING
COMPLETED
FAILED
```

Important fields include:

```text
payment
processor_behavior
processor_operation_id
status
attempts
available_at
lease_expires_at
started_at
completed_at
last_error
created_at
updated_at
```

The job lease allows expired processing work to be recovered.

---

# Payment Lifecycle

The normal payment lifecycle is:

```text
CREATED
   ↓
PROCESSING
   ↓
SUCCEEDED
```

or:

```text
CREATED
   ↓
PROCESSING
   ↓
FAILED
```

A retry does not automatically create another Payment.

Instead:

```text
Payment
   │
   ├── Attempt 1
   │
   ├── Attempt 2
   │
   └── Attempt 3
```

The logical payment remains the same.

---

# Idempotency Contract

The idempotency key is part of the API contract.

For a given idempotency key:

```text
Same key + same request
        ↓
same logical payment
```

while:

```text
Same key + different request
        ↓
reject request
```

The system must also behave correctly when identical requests arrive concurrently.

The database uniqueness constraint is therefore a correctness boundary, not merely an optimization.

---

# Concurrency Strategy

LedgerFlow uses database transactions and row-level locking where appropriate.

The central invariant is:

```text
One idempotency key
        ↓
One logical payment
```

The implementation does not rely on:

```python
if not exists():
    create()
```

alone.

Instead, correctness is enforced through:

* transaction boundaries;
* unique database constraints;
* recovery from uniqueness races;
* deterministic request fingerprinting.

---

# Worker Processing

Payment processing is separated from the HTTP request lifecycle.

Conceptually:

```text
HTTP request
     ↓
Create payment
     ↓
Queue job
     ↓
Return API response
```

Then:

```text
Worker
   ↓
Claim job
   ↓
Acquire lease
   ↓
Process payment
   ↓
Record processor result
   ↓
Complete or retry job
```

A job receives a lease while it is being processed.

If the worker disappears before completing the job:

```text
PROCESSING
     ↓
lease expires
     ↓
QUEUED
     ↓
another worker can recover it
```

---

# Processor Simulation

The processor simulator deliberately exposes different behaviors.

## SUCCESS

The processor operation succeeds.

Expected result:

```text
Payment → SUCCEEDED
Attempt → SUCCESS
Job → COMPLETED
```

---

## TRANSIENT_FAILURE

The processor records a failed operation and reports a temporary failure.

Expected behavior:

```text
Payment
   ↓
retry
   ↓
new processor operation
```

The logical payment remains unchanged.

---

## PERMANENT_FAILURE

The processor rejects the operation permanently.

Expected result:

```text
Payment → FAILED
Attempt → FAILED
Job → FAILED
```

No automatic retry should occur.

---

## UNKNOWN

The simulated processor completes the operation but LedgerFlow receives an unknown outcome.

Expected behavior:

```text
Payment Attempt → UNKNOWN
```

The processor operation identifier is preserved.

The system should reconcile the existing operation rather than blindly create another processor operation.

---

# Retry and Reconciliation

Retries and reconciliation are deliberately separate concepts.

A transient failure can be retried.

An unknown outcome requires determining what actually happened.

Conceptually:

```text
TRANSIENT_FAILURE
       ↓
      RETRY
       ↓
new processing attempt
```

while:

```text
UNKNOWN
   ↓
preserve operation ID
   ↓
query/reconcile processor state
   ↓
resolve existing attempt
```

This distinction prevents uncertainty from automatically becoming duplicate work.

---

# Reliability Invariants

LedgerFlow is evaluated against explicit invariants.

## Idempotency

```text
Same idempotency key
        +
same request
        ↓
same logical payment
```

## Request Consistency

```text
Same idempotency key
        +
different request
        ↓
reject
```

## Concurrency

Concurrent identical requests must not create multiple logical payments.

## Processor Operation Identity

When an operation has an uncertain outcome, reconciliation should preserve the original processor operation identity.

## Worker Recovery

A worker crash must not permanently strand a leased job.

## Retry Isolation

Transient retries must operate on the same logical payment.

## Permanent Failure

Permanent failures must not enter an automatic retry loop.

## Unknown Outcome

An unknown outcome must not be silently converted into a confirmed failure.

---

# Experiments

LedgerFlow is developed through controlled experiments rather than only feature implementation.

The project currently documents the following investigations.

---

# Experiment 1: Concurrency

## Question

Can concurrent identical payment requests create duplicate logical payments?

## Failure Mode

Two requests observe the same idempotency key before either transaction commits.

## Mechanism Tested

* database uniqueness;
* transactions;
* concurrent request handling.

## Evidence

The experiment records the resulting payment count and idempotency behavior.

See:

```text
experiments/concurrency/
```

---

# Experiment 2: Worker Crash Recovery

## Question

What happens when a worker crashes while processing a payment?

## Failure Point

The worker is intentionally interrupted after claiming the job.

A second failure point is also tested after processor execution.

## Mechanism Tested

* job lease;
* expired lease recovery;
* stable processor operation ID;
* idempotent processor behavior.

## Observed Recovery Model

A recovered job can reuse the same processor operation identity rather than blindly creating a second processor operation.

See:

```text
experiments/worker-crash/
```

---

# Experiment 3: Retry and Reconciliation

## Question

Can LedgerFlow distinguish retryable failures from terminal failures and uncertain outcomes?

## Behaviors Tested

```text
TRANSIENT_FAILURE
PERMANENT_FAILURE
UNKNOWN
```

## Mechanisms Tested

* exponential backoff;
* bounded retries;
* failure classification;
* operation identity;
* reconciliation.

See:

```text
experiments/retry-reconciliation/
```

---

# Experiment 4: Production Deployment Validation

LedgerFlow was deployed to Render using:

```text
Render Web Service
        +
Render PostgreSQL
```

The deployment uses:

```text
Django
Gunicorn
WhiteNoise
PostgreSQL
environment-based configuration
```

The deployment successfully reached:

```text
Deploy succeeded | Live
```

The application initially returned:

```text
Bad Request (400)
```

The cause was a mismatch between the configured Django hostname and the hostname assigned by Render.

The hostname configuration was corrected.

The public application subsequently became reachable.

This experiment demonstrated that:

> A successful build does not necessarily imply a correctly configured deployed application.

Deployment configuration is therefore treated as another engineering surface requiring explicit validation.

Detailed evidence is recorded in:

```text
experiments/production-deployment/
```

---

# Production Deployment

The project currently supports deployment to Render.

The deployment architecture is:

```text
GitHub
   ↓
Render Web Service
   ↓
Gunicorn
   ↓
Django
   ↓
Render PostgreSQL
```

The repository contains:

```text
build.sh
render.yaml
requirements.txt
```

The production environment uses environment variables for:

```text
DJANGO_ENV
DJANGO_DEBUG
DJANGO_SECRET_KEY
DJANGO_ALLOWED_HOSTS
DJANGO_CSRF_TRUSTED_ORIGINS
LEDGERFLOW_INLINE_WORKER
DATABASE_URL
```

Secrets are not stored in the repository.

---

# Free-Tier Processing Mode

Render's Free tier does not provide a continuously running background worker.

LedgerFlow therefore supports an optional deployment mode:

```text
LEDGERFLOW_INLINE_WORKER=true
```

In this mode, the simulator request can process the newly queued payment inline.

This exists specifically to make the reliability simulator demonstrable on a free hosted environment.

It is not equivalent to a durable production background-worker architecture.

The intended architecture remains:

```text
API
 ↓
durable job queue
 ↓
independent worker
 ↓
processor
```

The inline mode is a deployment compromise for demonstration.

---

# Local Development

## Requirements

* Python 3.14+
* PostgreSQL 17
* Docker Desktop
* Git

---

## Create the Environment

From the repository root:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

---

## Start PostgreSQL

The repository includes Docker Compose configuration.

```powershell
docker compose up -d
```

---

## Run Migrations

```powershell
python src/manage.py migrate
```

---

## Start Django

```powershell
python src/manage.py runserver
```

The local application will normally be available at:

```text
http://127.0.0.1:8000/
```

---

# Validation Commands

Run Django's system checks:

```powershell
python src/manage.py check
```

Run the test suite:

```powershell
python src/manage.py test
```

Run deployment checks:

```powershell
python src/manage.py check --deploy
```

Collect production static assets:

```powershell
python src/manage.py collectstatic --noinput
```

---

# Production Configuration Checks

Development and production environments use different configuration sources.

Local development can use:

```text
.env
```

The `.env` file is ignored by Git.

Production secrets are supplied through the deployment environment.

The application should never depend on a secret committed to the repository.

---

# Security Considerations

LedgerFlow is a simulator and deliberately does not process real payment information.

It should not be configured with:

* real card numbers;
* real payment credentials;
* real processor API keys;
* real financial accounts.

The production deployment exists for software-engineering demonstration.

The following security mechanisms are enabled for production:

* HTTPS redirect;
* secure session cookies;
* secure CSRF cookies;
* HSTS;
* content-type sniffing protection;
* restrictive frame policy;
* environment-based secret configuration.

---

# UI and Product Design

LedgerFlow's interface is designed as an operational engineering application.

The design goals are:

* clear information hierarchy;
* restrained typography;
* dense operational information;
* state visibility;
* minimal decorative UI;
* subtle state-aware motion;
* responsive layouts;
* strong payment detail visualization.

The simulator is treated as a developer/test harness rather than the product's conceptual center.

The main product surfaces are:

```text
Overview
Payments
Payment Detail
Simulator
System
```

The payment detail page is the primary reliability showcase.

It exposes the relationship between:

```text
Payment
   ↓
Job
   ↓
Payment Attempt
   ↓
Processor Operation
```

---

# Why Payment Detail Matters

A normal payment dashboard may only show:

```text
Payment
Amount
Status
```

LedgerFlow exposes the underlying reliability state.

A payment can show:

```text
Payment
   ├── Status
   ├── Idempotency key
   ├── Job
   │     ├── attempts
   │     ├── lease
   │     └── processing state
   │
   ├── Payment Attempts
   │     ├── status
   │     ├── failure type
   │     └── processor operation
   │
   └── Processor Operation
         ├── operation ID
         └── outcome
```

This makes the reliability mechanisms observable rather than hidden inside implementation code.

---

# Engineering Decisions

Several design decisions are intentional.

## Idempotency Is an API Property

It is not merely a database column.

The idempotency key defines the identity of a logical client operation.

---

## Database Constraints Enforce Correctness

Application-level checks alone are not sufficient for concurrent requests.

The database participates in the correctness model.

---

## Unknown Is Not a Payment State

A payment should not be marked `UNKNOWN` simply because an individual processor call has an uncertain result.

Uncertainty belongs to the processing attempt.

---

## Retries Do Not Necessarily Create New Payments

A retry can represent another attempt to resolve the same logical payment.

---

## Processor Operation Identity Is Preserved

When the outcome of an external operation is uncertain, its operation identity is retained for reconciliation.

---

## Worker Leases Provide Recoverability

A processing job must not remain permanently locked because a worker disappeared.

---

## Experiments Are Part of the Implementation

The project treats failure injection and measurement as first-class engineering activities.

A mechanism is not considered validated simply because the code compiles.

---

# Testing Philosophy

LedgerFlow uses multiple levels of validation.

## Unit and Application Tests

Validate:

* state transitions;
* idempotency;
* request fingerprinting;
* retry behavior;
* reconciliation;
* job processing.

## Concurrency Experiments

Validate:

* uniqueness under simultaneous requests;
* transactional behavior;
* duplicate prevention.

## Failure Injection

Validate:

* worker crash recovery;
* transient failures;
* permanent failures;
* unknown outcomes.

## Deployment Validation

Validate:

* build;
* runtime;
* database connectivity;
* public HTTP access;
* production configuration.

The objective is to validate behavior under failure rather than only the successful path.

---

# What LedgerFlow Does Not Claim

LedgerFlow is not:

* a real payment gateway;
* a PCI-compliant payment system;
* a replacement for Stripe, Adyen, PayPal, or a bank processor;
* a production financial infrastructure platform;
* a high-availability distributed payment network;
* a real-money transaction system.

The processor is simulated.

The value of the project is the investigation of reliability mechanisms and the experimental validation of those mechanisms.

---

# Current Deployment Limitations

The current free hosted deployment has important limitations.

The free PostgreSQL environment is intended for testing and prototyping.

The hosted application does not currently have a continuously running dedicated worker on the free tier.

The inline worker mode is therefore used for demonstration.

The deployment should not be interpreted as production-grade payment infrastructure.

For a higher-fidelity deployment, the next architecture would be:

```text
                    ┌───────────────┐
                    │   Web API     │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │  PostgreSQL   │
                    │   Job Queue   │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │ Worker Pool   │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │   Processor   │
                    └───────────────┘
```

---

# Future Engineering Work

Potential future investigations include:

## Multi-Worker Stress Testing

Measure behavior with multiple worker processes competing for jobs.

## Queue Starvation

Investigate whether certain jobs can be delayed indefinitely.

## Lease Duration Analysis

Measure the relationship between:

```text
processing duration
lease duration
worker failure
duplicate execution risk
```

## Processor Timeout Modeling

Introduce explicit network timeout behavior.

## Reconciliation Scheduling

Move reconciliation into a durable scheduled workflow.

## Observability

Add structured event records and metrics for:

```text
payment latency
retry rate
unknown outcomes
reconciliation rate
job age
lease expirations
processor failures
```

## Failure Budgets

Measure how reliability changes as processor failure rates increase.

## Load Testing

Measure:

```text
requests/sec
concurrent requests
database contention
queue depth
processing latency
duplicate rate
```

---

# Project Methodology

The project follows an investigation-driven engineering process.

```text
1. Identify a real reliability problem.

2. Research how production systems model the problem.

3. Define an explicit hypothesis.

4. Design the smallest mechanism capable of testing it.

5. Implement the mechanism.

6. Introduce controlled failure.

7. Observe the resulting system state.

8. Compare the result against explicit invariants.

9. Identify weaknesses.

10. Redesign.

11. Repeat the experiment.

12. Document the evidence.
```

This prevents LedgerFlow from becoming a feature checklist.

Each major subsystem exists because it addresses a specific failure mode.

---

# Documentation Map

Detailed engineering documentation is organized as follows.

```text
docs/problem.md
```

Defines the reliability problem and research motivation.

```text
docs/api-contract.md
```

Defines the idempotency and API contract.

```text
docs/payment-lifecycle.md
```

Defines payment and attempt state transitions.

```text
docs/data-model.md
```

Documents the database model.

```text
docs/concurrency.md
```

Documents concurrent request behavior and database guarantees.

```text
docs/retry-and-reconciliation.md
```

Documents retry classification, backoff, unknown outcomes, and reconciliation.

---

# Experiment Map

```text
experiments/concurrency/
```

Concurrency and idempotency validation.

```text
experiments/worker-crash/
```

Worker failure and lease recovery validation.

```text
experiments/retry-reconciliation/
```

Retry and uncertain processor outcome validation.

```text
experiments/production-deployment/
```

Hosted deployment and production-configuration validation.

Each experiment contains:

```text
README.md
results.md
```

The README defines the hypothesis and methodology.

The results file records observations and conclusions.

---

# Status

LedgerFlow currently has the following major components implemented:

```text
[x] Project structure
[x] PostgreSQL-backed persistence
[x] Payment model
[x] Idempotency records
[x] Request fingerprinting
[x] Payment attempts
[x] Processor operation model
[x] PostgreSQL-backed payment jobs
[x] Job leasing
[x] Worker processing
[x] Worker crash recovery
[x] Transient failure classification
[x] Permanent failure classification
[x] Exponential retry backoff
[x] Unknown processor outcomes
[x] Reconciliation
[x] Concurrency validation
[x] Retry/reconciliation validation
[x] Production configuration
[x] Static asset pipeline
[x] Gunicorn deployment
[x] Render deployment
[x] Production hostname validation
[x] Hosted application availability
```

The unchecked items are intentionally not marked complete until their corresponding experiments have been executed and recorded.

---

# Key Takeaway

LedgerFlow is an investigation into a deceptively difficult problem:

> How do you make a payment operation reliable when requests can be duplicated, responses can disappear, workers can crash, processors can fail, and the true outcome of an operation can temporarily be unknown?

The project answers that question through a combination of:

```text
Idempotency
+
Database constraints
+
Transactions
+
Explicit state machines
+
Payment attempts
+
Stable processor operation IDs
+
Worker leases
+
Bounded retries
+
Failure classification
+
Reconciliation
+
Controlled experiments
+
Production deployment validation
```
The central idea is that payment reliability cannot be achieved by simply adding retries.

The system must preserve the identity of the logical operation, distinguish confirmed outcomes from uncertain ones, make concurrent behavior safe, recover incomplete work, and provide enough state to reconstruct what happened.

LedgerFlow exists to make those mechanisms observable, testable, and measurable.