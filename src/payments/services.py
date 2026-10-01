from django.db import transaction
from django.utils import timezone

from .models import (
    Payment,
    PaymentAttempt,
    ProcessorOperation,
)
from .processor import (
    PermanentProcessorError,
    ProcessorSimulator,
    TransientProcessorError,
    UnknownProcessorOutcome,
)


processor = ProcessorSimulator()


def process_payment(payment, behavior="SUCCESS"):
    """
    Process one logical payment operation.

    A payment can have multiple attempts, but each invocation of the
    processor creates at most one processor operation.
    """

    with transaction.atomic():
        payment.status = Payment.Status.PROCESSING
        payment.save(
            update_fields=["status", "updated_at"]
        )

    try:
        operation_id, _ = processor.execute(behavior)

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
                update_fields=["status", "updated_at"]
            )

        return attempt

    except UnknownProcessorOutcome as exc:
        with transaction.atomic():
            attempt = PaymentAttempt.objects.create(
                payment=payment,
                processor_operation_id=exc.operation_id,
                status=PaymentAttempt.Status.UNKNOWN,
                failure_type="",
            )

        return attempt

    except TransientProcessorError as exc:
        with transaction.atomic():
            attempt = PaymentAttempt.objects.create(
                payment=payment,
                processor_operation_id="",
                status=PaymentAttempt.Status.FAILED,
                failure_type="TRANSIENT",
                error=str(exc),
                completed_at=timezone.now(),
            )

        return attempt

    except PermanentProcessorError as exc:
        with transaction.atomic():
            attempt = PaymentAttempt.objects.create(
                payment=payment,
                processor_operation_id="",
                status=PaymentAttempt.Status.FAILED,
                failure_type="PERMANENT",
                error=str(exc),
                completed_at=timezone.now(),
            )

            payment.status = Payment.Status.FAILED
            payment.save(
                update_fields=["status", "updated_at"]
            )

        return attempt


def reconcile_payment(payment):
    """
    Resolve UNKNOWN attempts by querying the original processor
    operation.

    Reconciliation never creates a new processor operation.
    """

    unknown_attempts = payment.attempts.filter(
        status=PaymentAttempt.Status.UNKNOWN
    )

    for attempt in unknown_attempts:
        processor_status = processor.get_status(
            attempt.processor_operation_id
        )

        if processor_status == ProcessorOperation.Outcome.SUCCESS:
            with transaction.atomic():
                attempt.status = PaymentAttempt.Status.SUCCESS
                attempt.completed_at = timezone.now()

                attempt.save(
                    update_fields=[
                        "status",
                        "completed_at",
                    ]
                )

                payment.status = Payment.Status.SUCCEEDED
                payment.save(
                    update_fields=[
                        "status",
                        "updated_at",
                    ]
                )

            return attempt

        if processor_status == ProcessorOperation.Outcome.FAILED:
            with transaction.atomic():
                attempt.status = PaymentAttempt.Status.FAILED
                attempt.completed_at = timezone.now()

                attempt.save(
                    update_fields=[
                        "status",
                        "completed_at",
                    ]
                )

                payment.status = Payment.Status.FAILED
                payment.save(
                    update_fields=[
                        "status",
                        "updated_at",
                    ]
                )

            return attempt

    return None


def retry_payment(payment, behavior="SUCCESS"):
    """
    Retry only a transiently failed processing attempt.

    Permanent failures, unknown outcomes, succeeded payments, and
    payments without a failed attempt are not retryable.
    """

    if payment.status != Payment.Status.PROCESSING:
        return None

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

    return process_payment(
        payment,
        behavior=behavior,
    )