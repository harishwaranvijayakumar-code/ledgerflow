# LedgerFlow Data Model

## Design Goal

The data model must represent a logical payment operation separately
from individual processing attempts.

This distinction is necessary because one payment may involve
multiple attempts due to retries, failures, or uncertain processor
outcomes.

## Core Entities

### Payment

Represents one logical payment operation.

A payment has:

- A unique payment identifier
- Customer information
- Amount
- Currency
- Current payment status
- Creation timestamp
- Update timestamp

### Idempotency Record

Associates a client-provided idempotency key with one logical
payment operation.

The same idempotency key must not create multiple logical payments.

The record should also allow LedgerFlow to detect reuse of the same
key with different request parameters.

### Payment Attempt

Represents an individual attempt to process a payment with the
external processor.

An attempt has:

- A unique attempt identifier
- The associated payment
- A processor operation identifier
- Attempt status
- Error information when applicable
- Creation timestamp
- Completion timestamp when applicable

A payment may have multiple attempts.

## Relationships

One customer may have many payments.

One payment has one idempotency record.

One payment may have multiple payment attempts.

Each payment attempt has a processor operation identifier.

## Current Hypothesis

The processor operation does not necessarily need to be a separate
database entity.

The processor operation identifier may initially belong to the
Payment Attempt.

This decision should be revisited if the processor simulation
becomes sufficiently complex to justify a separate model.

## Open Questions

- What exactly should be stored as the request fingerprint?
- Should the complete original response be stored?
- How should idempotency-key expiration work?
- What fields must be immutable?
- Which payment states are terminal?
- What constraints must the database enforce?

## Concurrency Invariants

The database must enforce that an idempotency key can identify only
one logical payment.

The application must ensure that:

- Concurrent requests with the same idempotency key resolve to the
  same logical payment.
- Reusing an idempotency key with different request parameters is
  rejected.
- A partially completed request does not leave inconsistent
  idempotency and payment records.
- Database transactions define the atomic boundary for creating the
  logical payment.