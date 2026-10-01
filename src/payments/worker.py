import uuid

from django.db import transaction

from .jobs import (
    MAX_JOB_ATTEMPTS,
    claim_next_job,
    complete_job,
    fail_job,
    retry_job,
)
from .models import Payment, PaymentAttempt
from .processor import (
    PermanentProcessorError,
    ProcessorSimulator,
    TransientProcessorError,
    UnknownProcessorOutcome,
)

processor = ProcessorSimulator()


def process_next_job(
    crash_after_claim=False,
    crash_after_processor=False,
):
    job = claim_next_job()

    if job is None:
        return None

    if not job.processor_operation_id:
        job.processor_operation_id = str(uuid.uuid4())

        job.save(
            update_fields=[
                "processor_operation_id",
                "updated_at",
            ]
        )

    if crash_after_claim:
        raise RuntimeError(
            "Simulated worker crash after job claim."
        )

    payment = job.payment

    try:
        with transaction.atomic():
            payment.status = Payment.Status.PROCESSING

            payment.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

        operation_id, outcome = processor.execute(
            behavior=job.processor_behavior,
            operation_id=job.processor_operation_id,
        )

        if crash_after_processor:
            raise RuntimeError(
                "Simulated worker crash after processor execution."
            )

        if outcome == "SUCCESS":
            with transaction.atomic():
                attempt = (
                    PaymentAttempt.objects
                    .filter(
                        payment=payment,
                        processor_operation_id=operation_id,
                    )
                    .first()
                )

                if attempt is None:
                    PaymentAttempt.objects.create(
                        payment=payment,
                        processor_operation_id=operation_id,
                        status=PaymentAttempt.Status.SUCCESS,
                        failure_type="",
                    )
                else:
                    attempt.status = (
                        PaymentAttempt.Status.SUCCESS
                    )
                    attempt.completed_at = None

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

                complete_job(job)

            return job

        raise RuntimeError(
            f"Unexpected processor outcome: {outcome}"
        )

    except UnknownProcessorOutcome as exc:
        with transaction.atomic():
            PaymentAttempt.objects.get_or_create(
                payment=payment,
                processor_operation_id=exc.operation_id,
                defaults={
                    "status": PaymentAttempt.Status.UNKNOWN,
                    "failure_type": "",
                },
            )

            fail_job(
                job,
                exc,
            )

        return job

    except TransientProcessorError as exc:
        with transaction.atomic():
            PaymentAttempt.objects.create(
                payment=payment,
                processor_operation_id=exc.operation_id,
                status=PaymentAttempt.Status.FAILED,
                failure_type="TRANSIENT",
                error=str(exc),
                completed_at=None,
            )

            if job.attempts < MAX_JOB_ATTEMPTS:
                retry_job(
                    job,
                    exc,
                )
            else:
                payment.status = Payment.Status.FAILED

                payment.save(
                    update_fields=[
                        "status",
                        "updated_at",
                    ]
                )

                fail_job(
                    job,
                    exc,
                )

        return job

    except PermanentProcessorError as exc:
        with transaction.atomic():
            PaymentAttempt.objects.create(
                payment=payment,
                processor_operation_id=exc.operation_id,
                status=PaymentAttempt.Status.FAILED,
                failure_type="PERMANENT",
                error=str(exc),
            )

            payment.status = Payment.Status.FAILED

            payment.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

            fail_job(
                job,
                exc,
            )

        return job