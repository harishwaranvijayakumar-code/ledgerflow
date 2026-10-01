from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import PaymentJob


JOB_LEASE_SECONDS = 30


def enqueue_payment(
    payment,
    processor_behavior="SUCCESS",
):
    job, created = PaymentJob.objects.get_or_create(
        payment=payment,
        defaults={
            "processor_behavior": processor_behavior,
            "status": PaymentJob.Status.QUEUED,
            "available_at": timezone.now(),
        },
    )

    if not created:
        return job, False

    return job, True


def claim_next_job():
    now = timezone.now()

    with transaction.atomic():
        job = (
            PaymentJob.objects
            .select_for_update(skip_locked=True)
            .filter(
                status=PaymentJob.Status.QUEUED,
                available_at__lte=now,
            )
            .order_by("created_at")
            .first()
        )

        if job is None:
            return None

        job.status = PaymentJob.Status.PROCESSING
        job.started_at = now
        job.lease_expires_at = (
            now + timedelta(seconds=JOB_LEASE_SECONDS)
        )
        job.attempts += 1

        job.save(
            update_fields=[
                "status",
                "started_at",
                "lease_expires_at",
                "attempts",
                "updated_at",
            ]
        )

        return job


def complete_job(job):
    job.status = PaymentJob.Status.COMPLETED
    job.completed_at = timezone.now()
    job.lease_expires_at = None

    job.save(
        update_fields=[
            "status",
            "completed_at",
            "lease_expires_at",
            "updated_at",
        ]
    )


def fail_job(job, error):
    job.status = PaymentJob.Status.FAILED
    job.last_error = str(error)
    job.completed_at = timezone.now()
    job.lease_expires_at = None

    job.save(
        update_fields=[
            "status",
            "last_error",
            "completed_at",
            "lease_expires_at",
            "updated_at",
        ]
    )


def recover_expired_jobs():
    now = timezone.now()

    with transaction.atomic():
        expired_jobs = list(
            PaymentJob.objects
            .select_for_update(skip_locked=True)
            .filter(
                status=PaymentJob.Status.PROCESSING,
                lease_expires_at__lt=now,
            )
        )

        for job in expired_jobs:
            job.status = PaymentJob.Status.QUEUED
            job.available_at = now
            job.lease_expires_at = None
            job.last_error = (
                "Worker lease expired before job completion."
            )

            job.save(
                update_fields=[
                    "status",
                    "available_at",
                    "lease_expires_at",
                    "last_error",
                    "updated_at",
                ]
            )

    return expired_jobs