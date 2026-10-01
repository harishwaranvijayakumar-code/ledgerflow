from django.db import transaction
from django.utils import timezone

from .models import Payment, PaymentAttempt
from .processor import (
    PermanentProcessorError,
    ProcessorSimulator,
    TransientProcessorError,
    UnknownProcessorOutcome,
)


processor = ProcessorSimulator()


def process_payment(payment, behavior="SUCCESS"):
    with transaction.atomic():
        payment.status = Payment.Status.PROCESSING
        payment.save(update_fields=["status", "updated_at"])

    try:
        operation_id, _ = processor.execute(behavior)

        with transaction.atomic():
            attempt = PaymentAttempt.objects.create(
                payment=payment,
                processor_operation_id=operation_id,
                status=PaymentAttempt.Status.SUCCESS,
                completed_at=timezone.now(),
            )

            payment.status = Payment.Status.SUCCEEDED
            payment.save(update_fields=["status", "updated_at"])

        return attempt

    except UnknownProcessorOutcome as exc:
        with transaction.atomic():
            attempt = PaymentAttempt.objects.create(
                payment=payment,
                processor_operation_id=exc.operation_id,
                status=PaymentAttempt.Status.UNKNOWN,
            )

        return attempt

    except TransientProcessorError as exc:
        with transaction.atomic():
            attempt = PaymentAttempt.objects.create(
                payment=payment,
                processor_operation_id="",
                status=PaymentAttempt.Status.FAILED,
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
                error=str(exc),
                completed_at=timezone.now(),
            )

            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status", "updated_at"])

        return attempt