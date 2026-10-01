# Worker Crash Recovery Results

## Experiment

Crash the worker immediately after successful processor execution.

## Observed Failure State

The worker terminated after the processor created the operation but before LedgerFlow committed the payment attempt.

Observed state:

- Payment: PROCESSING
- Job: PROCESSING
- Processor operation: present
- Payment attempts: 0

## Recovery

The job lease was manually expired.

A new worker recovered the job and processed it using the existing processor operation ID.

## Final State

- Payment: SUCCEEDED
- Job: COMPLETED
- Payment attempts: 1
- Processor operations for the operation ID: 1
- PaymentAttempt processor operation ID: same as original operation ID

## Conclusion

The crash-recovery path preserved the original processor operation identity and avoided creating a duplicate processor operation.