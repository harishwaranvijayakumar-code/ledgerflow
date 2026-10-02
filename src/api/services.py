import hashlib
import json
import uuid
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.utils import timezone

from payments.jobs import (
    MAX_JOB_ATTEMPTS,
    enqueue_payment,
    retry_job,
)
from payments.models import (
    IdempotencyRecord,
    Payment,
    PaymentAttempt,
    PaymentJob,
    ProcessorOperation,
)
from payments.processor import (
    PermanentProcessorError,
    ProcessorSimulator,
    TransientProcessorError,
    UnknownProcessorOutcome,
)


class InvalidPaymentRequest(Exception):
    pass


class IdempotencyConflict(Exception):
    pass


processor = ProcessorSimulator()


def normalize_payment_request(data):
    amount = data.get("amount")
    currency = data.get("currency")

    if amount is None or currency is None:
        raise InvalidPaymentRequest(
            "amount and currency are required"
        )

    try:
        amount = Decimal(str(amount))
    except (InvalidOperation, ValueError):
        raise InvalidPaymentRequest(
            "amount must be a valid number"
        )

    if amount <= 0:
        raise InvalidPaymentRequest(
            "amount must be greater than zero"
        )

    currency = str(currency).upper()

    if len(currency) != 3 or not currency.isalpha():
        raise InvalidPaymentRequest(
            "currency must be a 3-letter code"
        )

    return {
        "amount": format(amount, ".2f"),
        "currency": currency,
    }


def fingerprint_request(data):
    canonical = json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        canonical.encode()
    ).hexdigest()


def serialize_payment(payment):
    return {
        "id": payment.id,
        "amount": str(payment.amount),
        "currency": payment.currency,
        "status": payment.status,
        "created_at": payment.created_at.isoformat(),
        "updated_at": payment.updated_at.isoformat(),
    }


def create_or_get_payment(idempotency_key, data):
    if not idempotency_key:
        raise InvalidPaymentRequest(
            "Idempotency-Key is required"
        )

    normalized = normalize_payment_request(data)
    fingerprint = fingerprint_request(normalized)

    existing = (
        IdempotencyRecord.objects
        .select_related("payment")
        .filter(key=idempotency_key)
        .first()
    )

    if existing:
        if existing.request_fingerprint != fingerprint:
            raise IdempotencyConflict(
                "Idempotency-Key was already used with "
                "different request data"
            )

        return existing.payment, False

    try:
        with transaction.atomic():
            payment = Payment.objects.create(
                amount=normalized["amount"],
                currency=normalized["currency"],
                status=Payment.Status.CREATED,
            )

            IdempotencyRecord.objects.create(
                key=idempotency_key,
                payment=payment,
                request_fingerprint=fingerprint,
            )

        return payment, True

    except IntegrityError:
        existing = (
            IdempotencyRecord.objects
            .select_related("payment")
            .get(key=idempotency_key)
        )

        if existing.request_fingerprint != fingerprint:
            raise IdempotencyConflict(
                "Idempotency-Key was already used with "
                "different request data"
            )

        return existing.payment, False


def process_payment(payment, behavior="SUCCESS"):
    """
    Legacy synchronous processing helper retained for the
    reliability test suite and direct service-level experiments.

    The production web flow uses PaymentJob + worker processing.
    """

    operation_id = str(uuid.uuid4())

    with transaction.atomic():
        payment.status = Payment.Status.PROCESSING
        payment.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

    try:
        operation_id, outcome = processor.execute(
            behavior=behavior,
            operation_id=operation_id,
        )

        if outcome == "SUCCESS":
            with transaction.atomic():
                attempt = PaymentAttempt.objects.create(
                    payment=payment,
                    processor_operation_id=operation_id,
                    status=PaymentAttempt.Status.SUCCESS,
                    failure_type="",
                    completed_at=timezone.now(),
                )

                payment.status = Payment.Status.SUCCEEDED
                payment.save(
                    update_fields=[
                        "status",
                        "updated_at",
                    ]
                )

            return attempt

        raise RuntimeError(
            f"Unexpected processor outcome: {outcome}"
        )

    except UnknownProcessorOutcome as exc:
        with transaction.atomic():
            attempt = PaymentAttempt.objects.create(
                payment=payment,
                processor_operation_id=exc.operation_id,
                status=PaymentAttempt.Status.UNKNOWN,
                failure_type="",
                error=str(exc),
            )

            payment.status = Payment.Status.PROCESSING
            payment.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

        return attempt

    except TransientProcessorError as exc:
        with transaction.atomic():
            attempt = PaymentAttempt.objects.create(
                payment=payment,
                processor_operation_id=exc.operation_id,
                status=PaymentAttempt.Status.FAILED,
                failure_type="TRANSIENT",
                error=str(exc),
            )

            payment.status = Payment.Status.PROCESSING
            payment.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

        return attempt

    except PermanentProcessorError as exc:
        with transaction.atomic():
            attempt = PaymentAttempt.objects.create(
                payment=payment,
                processor_operation_id=exc.operation_id,
                status=PaymentAttempt.Status.FAILED,
                failure_type="PERMANENT",
                error=str(exc),
                completed_at=timezone.now(),
            )

            payment.status = Payment.Status.FAILED
            payment.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

        return attempt


def reconcile_payment(payment):
    """
    Resolve an UNKNOWN processor attempt by querying the
    original processor operation.

    Reconciliation never creates a new processor operation.
    """

    unknown_attempt = (
        payment.attempts
        .filter(
            status=PaymentAttempt.Status.UNKNOWN
        )
        .order_by("-created_at")
        .first()
    )

    if unknown_attempt is None:
        return None

    operation_id = unknown_attempt.processor_operation_id

    outcome = processor.get_status(operation_id)

    if outcome is None:
        return unknown_attempt

    with transaction.atomic():
        if outcome == ProcessorOperation.Outcome.SUCCESS:
            unknown_attempt.status = PaymentAttempt.Status.SUCCESS
            unknown_attempt.completed_at = timezone.now()
            unknown_attempt.error = ""
            unknown_attempt.save(
                update_fields=[
                    "status",
                    "completed_at",
                    "error",
                ]
            )

            payment.status = Payment.Status.SUCCEEDED
            payment.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

            try:
                job = payment.job
            except PaymentJob.DoesNotExist:
                job = None

            if (
                job is not None
                and job.status
                in {
                    PaymentJob.Status.QUEUED,
                    PaymentJob.Status.PROCESSING,
                    PaymentJob.Status.FAILED,
                }
            ):
                job.status = PaymentJob.Status.COMPLETED
                job.completed_at = timezone.now()
                job.lease_expires_at = None
                job.last_error = ""
                job.save(
                    update_fields=[
                        "status",
                        "completed_at",
                        "lease_expires_at",
                        "last_error",
                        "updated_at",
                    ]
                )

        elif outcome == ProcessorOperation.Outcome.FAILED:
            unknown_attempt.status = PaymentAttempt.Status.FAILED
            unknown_attempt.failure_type = "PERMANENT"
            unknown_attempt.completed_at = timezone.now()
            unknown_attempt.error = (
                "Processor reconciliation confirmed failure."
            )
            unknown_attempt.save(
                update_fields=[
                    "status",
                    "failure_type",
                    "completed_at",
                    "error",
                ]
            )

            payment.status = Payment.Status.FAILED
            payment.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

            try:
                job = payment.job
            except PaymentJob.DoesNotExist:
                job = None

            if job is not None:
                job.status = PaymentJob.Status.FAILED
                job.completed_at = timezone.now()
                job.lease_expires_at = None
                job.last_error = (
                    "Processor reconciliation confirmed failure."
                )
                job.save(
                    update_fields=[
                        "status",
                        "completed_at",
                        "lease_expires_at",
                        "last_error",
                        "updated_at",
                    ]
                )

    unknown_attempt.refresh_from_db()

    return unknown_attempt


def retry_payment(payment, behavior="SUCCESS"):
    """
    Manually retry a payment after a transient failure.

    The logical Payment remains the same. A new processor
    execution is created by the worker.
    """

    latest_attempt = (
        payment.attempts
        .order_by("-created_at")
        .first()
    )

    if latest_attempt is None:
        return None

    if latest_attempt.status != PaymentAttempt.Status.FAILED:
        return None

    if latest_attempt.failure_type != "TRANSIENT":
        return None

    try:
        job = payment.job
    except PaymentJob.DoesNotExist:
        job = None

    if job is None:
        return process_payment(
            payment,
            behavior=behavior,
        )

    now = timezone.now()

    job.status = PaymentJob.Status.QUEUED
    job.processor_behavior = behavior
    job.available_at = now
    job.lease_expires_at = None
    job.completed_at = None
    job.last_error = ""
    job.processor_operation_id = ""

    job.save(
        update_fields=[
            "status",
            "processor_behavior",
            "available_at",
            "lease_expires_at",
            "completed_at",
            "last_error",
            "processor_operation_id",
            "updated_at",
        ]
    )

    return job