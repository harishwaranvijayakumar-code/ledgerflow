# Worker Crash Recovery Experiment

## Hypothesis

If a worker crashes after the processor has executed a payment operation but before LedgerFlow records the result, the payment can be recovered without creating a second processor operation.

## Failure Window

The experiment intentionally crashes the worker after processor execution and before the database transaction records the PaymentAttempt.

## Expected Behavior

1. Payment remains PROCESSING.
2. PaymentJob remains PROCESSING.
3. The job retains its lease.
4. ProcessorOperation exists.
5. No PaymentAttempt exists yet.
6. The lease is allowed to expire.
7. Recovery moves the job back to QUEUED.
8. A new worker claims the job.
9. The original processor operation ID is reused.
10. Payment becomes SUCCEEDED.
11. Exactly one processor operation exists.
12. Exactly one PaymentAttempt exists.

## Why This Matters

A worker timeout or crash does not prove that the external operation failed.

The recovery mechanism therefore reuses the processor operation identity instead of blindly creating a second operation.