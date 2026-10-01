# Concurrency Model

## Problem

Two clients can submit the same logical payment simultaneously.

A naive implementation can perform:

```text
check whether idempotency key exists
if not:
    create payment