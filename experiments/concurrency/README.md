# Concurrent Idempotency Experiment

## Objective

Determine whether simultaneous requests using the same idempotency key create exactly one logical Payment.

## Hypothesis

For N concurrent requests with the same idempotency key and identical request data:

- exactly one Payment is created
- exactly one IdempotencyRecord is created
- every request resolves to the same Payment
- exactly one request reports `created=True`
- all other requests replay the existing Payment

## Experimental setup

- Database: PostgreSQL
- Workers: 10 Python threads
- Idempotency key: `concurrent-test-key`
- Amount: `250.00`
- Currency: `USD`

## Expected invariant

```text
errors == 0
Payment.objects.count() == 1
IdempotencyRecord.objects.count() == 1
unique(payment_ids) == 1
created_count == 1