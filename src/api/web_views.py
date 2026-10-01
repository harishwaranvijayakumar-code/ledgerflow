import os

from django.shortcuts import get_object_or_404, redirect, render

from payments.jobs import enqueue_payment
from payments.models import Payment, PaymentAttempt, PaymentJob
from payments.worker import process_next_job

from .services import (
    IdempotencyConflict,
    InvalidPaymentRequest,
    create_or_get_payment,
)


def _metrics():
    payments = Payment.objects.all()
    attempts = PaymentAttempt.objects.all()
    jobs = PaymentJob.objects.all()

    total = payments.count()
    succeeded = payments.filter(status=Payment.Status.SUCCEEDED).count()
    processing = payments.filter(status=Payment.Status.PROCESSING).count()
    failed = payments.filter(status=Payment.Status.FAILED).count()
    created = payments.filter(status=Payment.Status.CREATED).count()

    success_rate = round((succeeded / total) * 100, 1) if total else 0

    unknown_attempts = attempts.filter(
        status=PaymentAttempt.Status.UNKNOWN
    ).count()

    transient_failures = attempts.filter(
        failure_type="TRANSIENT"
    ).count()

    permanent_failures = attempts.filter(
        failure_type="PERMANENT"
    ).count()

    retry_attempts = 0

    for payment in payments.prefetch_related("attempts"):
        attempt_count = len(payment.attempts.all())

        if attempt_count > 1:
            retry_attempts += attempt_count - 1

    queued_jobs = jobs.filter(
        status=PaymentJob.Status.QUEUED
    ).count()

    processing_jobs = jobs.filter(
        status=PaymentJob.Status.PROCESSING
    ).count()

    completed_jobs = jobs.filter(
        status=PaymentJob.Status.COMPLETED
    ).count()

    failed_jobs = jobs.filter(
        status=PaymentJob.Status.FAILED
    ).count()

    recovered_jobs = jobs.filter(
        last_error__icontains="lease expired"
    ).count()

    processing_durations = []

    for job in jobs.filter(
        started_at__isnull=False,
        completed_at__isnull=False,
    ).only(
        "started_at",
        "completed_at",
    ):
        duration = (
            job.completed_at - job.started_at
        ).total_seconds()

        processing_durations.append(duration)

    average_processing_seconds = (
        round(
            sum(processing_durations)
            / len(processing_durations),
            2,
        )
        if processing_durations
        else 0
    )

    attempt_total = attempts.count()

    unknown_rate = (
        round((unknown_attempts / attempt_total) * 100, 1)
        if attempt_total
        else 0
    )

    transient_failure_rate = (
        round((transient_failures / attempt_total) * 100, 1)
        if attempt_total
        else 0
    )

    permanent_failure_rate = (
        round((permanent_failures / attempt_total) * 100, 1)
        if attempt_total
        else 0
    )

    recovery_rate = (
        round((recovered_jobs / completed_jobs) * 100, 1)
        if completed_jobs
        else 0
    )

    return {
        "total": total,
        "created": created,
        "succeeded": succeeded,
        "processing": processing,
        "failed": failed,
        "success_rate": success_rate,
        "attempts": attempt_total,
        "retry_attempts": retry_attempts,
        "unknown_attempts": unknown_attempts,
        "transient_failures": transient_failures,
        "permanent_failures": permanent_failures,
        "queued_jobs": queued_jobs,
        "processing_jobs": processing_jobs,
        "completed_jobs": completed_jobs,
        "failed_jobs": failed_jobs,
        "recovered_jobs": recovered_jobs,
        "average_processing_seconds": average_processing_seconds,
        "unknown_rate": unknown_rate,
        "transient_failure_rate": transient_failure_rate,
        "permanent_failure_rate": permanent_failure_rate,
        "recovery_rate": recovery_rate,
    }


def dashboard(request):
    recent_payments = (
        Payment.objects
        .select_related(
            "idempotency_record",
            "job",
        )
        .prefetch_related("attempts")
        .order_by("-created_at")[:8]
    )

    return render(
        request,
        "dashboard.html",
        {
            "metrics": _metrics(),
            "recent_payments": recent_payments,
        },
    )


def payments_page(request):
    payments = (
        Payment.objects
        .select_related(
            "idempotency_record",
            "job",
        )
        .prefetch_related("attempts")
        .order_by("-created_at")
    )

    return render(
        request,
        "payments.html",
        {
            "payments": payments,
            "metrics": _metrics(),
        },
    )


def payment_detail(request, payment_id):
    payment = get_object_or_404(
        Payment.objects.select_related(
            "idempotency_record",
            "job",
        ),
        id=payment_id,
    )

    attempts = payment.attempts.order_by("created_at")
    latest_attempt = attempts.last()

    processing_seconds = None

    if (
        payment.job
        and payment.job.started_at
        and payment.job.completed_at
    ):
        processing_seconds = round(
            (
                payment.job.completed_at
                - payment.job.started_at
            ).total_seconds(),
            2,
        )

    return render(
        request,
        "payment_detail.html",
        {
            "payment": payment,
            "attempts": attempts,
            "latest_attempt": latest_attempt,
            "processing_seconds": processing_seconds,
            "metrics": _metrics(),
        },
    )


def simulator_page(request):
    if request.method == "POST":
        amount = request.POST.get("amount")
        currency = request.POST.get("currency")
        idempotency_key = request.POST.get("idempotency_key")
        processor_behavior = request.POST.get(
            "processor_behavior",
            "SUCCESS",
        )

        data = {
            "amount": amount,
            "currency": currency,
        }

        try:
            payment, created = create_or_get_payment(
                idempotency_key,
                data,
            )

            if created:
                enqueue_payment(
                    payment,
                    processor_behavior=processor_behavior,
                )

                inline_worker_enabled = (
                    os.getenv(
                        "LEDGERFLOW_INLINE_WORKER",
                        "false",
                    ).strip().lower()
                    in {
                        "1",
                        "true",
                        "yes",
                        "on",
                    }
                )

                if inline_worker_enabled:
                    process_next_job()

            return redirect(
                "payment-detail",
                payment_id=payment.id,
            )

        except InvalidPaymentRequest as exc:
            return render(
                request,
                "simulator.html",
                {
                    "metrics": _metrics(),
                    "error": str(exc),
                    "form_data": request.POST,
                },
            )

        except IdempotencyConflict as exc:
            return render(
                request,
                "simulator.html",
                {
                    "metrics": _metrics(),
                    "error": str(exc),
                    "form_data": request.POST,
                },
            )

    return render(
        request,
        "simulator.html",
        {
            "metrics": _metrics(),
        },
    )


def system_page(request):
    return render(
        request,
        "system.html",
        {
            "metrics": _metrics(),
        },
    )