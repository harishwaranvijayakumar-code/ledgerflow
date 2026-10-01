# Production Deployment Validation

## Objective

Validate that LedgerFlow can be deployed to a hosted production-like environment and that the deployed application is reachable through its public URL.

This experiment extends the earlier reliability experiments from local development into a real hosted environment.

The objective is not to prove that LedgerFlow is production-ready for real payment processing. LedgerFlow remains a payment reliability simulator. The objective is to verify that the engineered application, database, static assets, production configuration, and hosted runtime work together outside the local development environment.

---

## Environment

### Application

- Framework: Django
- Python: 3.14
- Application server: Gunicorn
- Static file serving: WhiteNoise
- Database: PostgreSQL
- Deployment platform: Render
- Deployment model: Free Web Service + Free PostgreSQL
- Processing mode: Inline worker

### Production configuration

The deployed application uses:

- `DJANGO_ENV=production`
- `DJANGO_DEBUG=false`
- Render-generated Django secret key
- Render PostgreSQL `DATABASE_URL`
- Render hostname configuration
- `LEDGERFLOW_INLINE_WORKER=true`

The inline worker exists because Render's Free tier does not provide the background-worker service required for a continuously running asynchronous worker.

This mode is intended for demonstration and validation rather than production asynchronous processing.

---

## Hypothesis

If the LedgerFlow application is correctly configured for a hosted environment, then:

1. The application should build successfully on the deployment platform.
2. Gunicorn should start the Django application.
3. Django should connect successfully to PostgreSQL.
4. Static assets should be served correctly.
5. The public application URL should return the LedgerFlow interface.
6. A payment created through the deployed simulator should be persisted in PostgreSQL and processed by the configured worker mode.
7. Payment state, attempts, processor operations, and job state should remain consistent with the reliability model developed locally.

---

## Validation Procedure

### Phase 1: Build

Deploy the `master` branch to Render.

Verify:

- dependencies install successfully;
- Django migrations complete;
- static files collect successfully;
- Gunicorn starts.

### Phase 2: Runtime

Verify:

- Render reports the service as Live;
- Gunicorn is listening;
- Django responds to HTTP requests;
- the public Render URL is reachable.

### Phase 3: Application smoke test

Using the deployed LedgerFlow interface:

1. Open the dashboard.
2. Open the simulator.
3. Create a successful test payment.
4. Confirm the payment reaches `SUCCEEDED`.
5. Open payment detail.
6. Confirm the payment attempt and processor operation are displayed.
7. Open the Payments page.
8. Confirm the payment appears in the transaction list.
9. Confirm dashboard metrics reflect the new payment.

### Phase 4: Reliability validation

After the basic smoke test passes, validate selected simulator behaviors:

- successful processing;
- transient processor failure;
- retry behavior;
- permanent processor failure;
- unknown processor outcome;
- reconciliation.

Crash-injection experiments should remain primarily local because the hosted free-tier environment is not an appropriate place for destructive worker experiments.

---

## Success Criteria

The deployment is considered successful when:

- the Render deployment reaches `Live`;
- Gunicorn starts without application startup errors;
- Django serves the public application;
- PostgreSQL is reachable;
- the LedgerFlow UI loads;
- a test payment can be created;
- the payment is persisted;
- the worker mode processes the payment;
- the resulting state matches the reliability model.

A deployment being reachable does not by itself prove that payment processing is correct.

---

## Engineering Significance

The deployment experiment tests a different failure surface from the earlier local experiments.

Local experiments primarily validated:

- database concurrency;
- idempotency;
- worker leases;
- retries;
- crash recovery;
- reconciliation.

The production deployment validates whether those components remain operational when placed behind:

- a hosted HTTP endpoint;
- a production WSGI server;
- environment-based configuration;
- a hosted PostgreSQL database;
- a production static-file pipeline.

This separates application correctness from local-environment correctness.

---

## Limitations

This deployment does not represent a real payment processor integration.

It also does not provide:

- real money movement;
- real payment credentials;
- a continuously running free-tier worker;
- production-grade background processing;
- production database backups;
- high availability;
- payment-provider guarantees.

Render's Free PostgreSQL instance is intended for testing and prototyping and has a limited lifetime.

The inline worker is a deployment demonstration mechanism and should not be treated as equivalent to a durable asynchronous worker architecture.

---

## Expected Evidence

The experiment should retain:

- deployment status;
- build/runtime logs;
- public application URL;
- successful payment ID;
- payment status;
- job status;
- payment attempt count;
- processor operation count;
- screenshots where useful;
- final experiment results.

---

## Conclusion

The deployment experiment determines whether LedgerFlow's locally validated reliability architecture can be operated through a hosted production-like environment.

The deployment itself is only one layer of validation. Functional payment processing and reliability behavior must be validated separately after the application is reachable.