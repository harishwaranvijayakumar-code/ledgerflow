from django.db import transaction
from django.utils import timezone

from .models import (
    Payment,
    PaymentAttempt,
    PaymentJob,
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
    Legacy synchronous processing helper.

    The production API uses PaymentJob + worker processing.
    This function remains useful for reliability tests and
    backwards-compatible service behavior.
    """
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
        )

        if outcome != "SUCCESS":
            raise RuntimeError(
                f"Unexpected processor outcome: {outcome}"
            )

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
                processor_operation_id=exc.operation_id,
                status=PaymentAttempt.Status.FAILED,
                failure_type="TRANSIENT",
                error=str(exc),
                completed_at=None,
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
    Resolve UNKNOWN payment attempts by querying the original
    processor operation.

    Reconciliation never creates a new processor operation.
    """
    unknown_attempts = (
        payment.attempts
        .filter(
            status=PaymentAttempt.Status.UNKNOWN,
        )
        .order_by("created_at")
    )

    for attempt in unknown_attempts:
        processor_status = processor.get_status(
            attempt.processor_operation_id
        )

        if processor_status is None:
            continue

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

                job = (
                    PaymentJob.objects
                    .filter(payment=payment)
                    .first()
                )

                if job is not None:
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

            return attempt

        if processor_status == ProcessorOperation.Outcome.FAILED:
            with transaction.atomic():
                attempt.status = PaymentAttempt.Status.FAILED
                attempt.failure_type = "PERMANENT"
                attempt.completed_at = timezone.now()

                attempt.save(
                    update_fields=[
                        "status",
                        "failure_type",
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

                job = (
                    PaymentJob.objects
                    .filter(payment=payment)
                    .first()
                )

                if job is not None:
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

            return attempt

    return None


def retry_payment(payment, behavior="SUCCESS"):
    """
    Retry a transiently failed payment.

    Async payments are requeued through PaymentJob.

    Legacy payments without a PaymentJob use the original
    synchronous processing helper so existing service behavior
    remains compatible.
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

    job = (
        PaymentJob.objects
        .filter(payment=payment)
        .first()
    )

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