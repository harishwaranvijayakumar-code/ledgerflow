# Concurrency Results

## Test configuration

| Parameter | Value |
|---|---|
| Database | PostgreSQL |
| Concurrent workers | 10 |
| Idempotency key | `concurrent-test-key` |
| Amount | `250.00 USD` |
| Expected Payments | 1 |
| Expected Idempotency Records | 1 |
| Expected creators | 1 |

## Result

The PostgreSQL concurrency test passed repeatedly.

Each successful run satisfied:

```text
errors = 0
results = 10
payments = 1
idempotency_records = 1
unique_payment_ids = 1
created_count = 1