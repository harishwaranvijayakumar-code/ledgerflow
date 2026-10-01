# Payment Lifecycle

## Payment States

## State Transitions

## Successful Payment

## Failed Payment

## Retry Behavior

## Open Questions
- Which failures are retryable?
- Which failures are permanent?
- Should retry state be part of the payment state?
- How long can a payment remain PROCESSING?
- What should happen if the application crashes while processing?
- What should a client receive when it retries a PROCESSING payment?

## Failure Classification

### Transient Failures

Failures that may resolve without changing the payment request.

Examples:

- Network timeout
- Temporary downstream service failure
- Temporary infrastructure failure

These may be retryable.

### Permanent Failures

Failures caused by an invalid or unacceptable payment request.

Examples:

- Invalid amount
- Invalid currency
- Unknown customer
- Malformed request

These should not be automatically retried.

### Important Rule

A retry of a request does not create a new logical payment.

The idempotency key identifies the logical payment operation across request attempts.

## Retry While Processing

If a client retries a payment while the existing payment is still
PROCESSING, LedgerFlow must not create another payment.

LedgerFlow returns the existing payment with:

- HTTP 202 Accepted
- The existing payment ID
- Status: PROCESSING

The client may retry again using the same idempotency key.

Once the payment reaches a terminal state, subsequent requests
using the same idempotency key return the existing result.

PROCESSING → SUCCEEDED

or

PROCESSING → FAILED

## Crash During Processing

A payment may remain in PROCESSING when the application crashes.

After recovery, LedgerFlow may not immediately know whether the
underlying payment operation completed.

LedgerFlow must therefore distinguish between:

- Known successful operations
- Known failed operations
- Operations that remain in progress
- Operations whose outcome is temporarily uncertain

The system must not create a second logical payment simply because
the original operation has an uncertain outcome.

The recovery mechanism will be determined during system design.

## External Payment Processor

LedgerFlow treats the payment processor as an external and
potentially unreliable dependency.

A timeout or connection failure does not necessarily mean that the
processor did not receive or complete the operation.

Therefore, LedgerFlow must not interpret every communication failure
as proof that the payment failed.

The system must distinguish between:

- Confirmed success
- Confirmed failure
- Temporary communication failure
- Unknown outcome

## Unknown Processing Outcomes

An unknown processor outcome should not automatically become a
payment state.

A communication failure may leave LedgerFlow uncertain about what
happened at the external processor.

LedgerFlow should therefore distinguish:

- Payment state
- Processing attempt state

A payment may have multiple processing attempts.

For example:

Payment:
    PROCESSING → SUCCEEDED

Attempts:
    Attempt 1 → UNKNOWN
    Attempt 2 → SUCCESS

This allows LedgerFlow to preserve the history of uncertain
processor interactions without unnecessarily expanding the payment
state machine.

## Unknown Processor Outcomes

When a processor attempt has an UNKNOWN outcome, LedgerFlow must not
blindly create a new processor operation.

The original processor operation should have a durable identifier
that can be used to determine its eventual outcome.

The recovery process is:

1. Record the attempt as UNKNOWN.
2. Preserve the processor operation identifier.
3. Determine the outcome of the original operation.
4. Update the payment based on the recovered result.

Possible recovered outcomes are:

- SUCCESS
- FAILED