from django.shortcuts import get_object_or_404, redirect, render

from payments.jobs import enqueue_payment
from payments.models import Payment, PaymentAttempt

from .services import (
    IdempotencyConflict,
    InvalidPaymentRequest,
    create_or_get_payment,
)


def _metrics():
    payments = Payment.objects.all()

    total = payments.count()
    succeeded = payments.filter(
        status=Payment.Status.SUCCEEDED
    ).count()
    processing = payments.filter(
        status=Payment.Status.PROCESSING
    ).count()
    failed = payments.filter(
        status=Payment.Status.FAILED
    ).count()

    success_rate = (
        round((succeeded / total) * 100, 1)
        if total
        else 0
    )

    attempts = PaymentAttempt.objects.all()

    unknown_attempts = attempts.filter(
        status=PaymentAttempt.Status.UNKNOWN
    ).count()

    return {
        "total": total,
        "succeeded": succeeded,
        "processing": processing,
        "failed": failed,
        "success_rate": success_rate,
        "attempts": attempts.count(),
        "unknown_attempts": unknown_attempts,
    }


def dashboard(request):
    recent_payments = (
        Payment.objects
        .select_related("idempotency_record")
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
        .select_related("idempotency_record")
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
            "idempotency_record"
        ),
        id=payment_id,
    )

    attempts = payment.attempts.order_by(
        "created_at"
    )

    return render(
        request,
        "payment_detail.html",
        {
            "payment": payment,
            "attempts": attempts,
        },
    )


def simulator_page(request):
    if request.method == "POST":
        amount = request.POST.get("amount")
        currency = request.POST.get("currency")
        idempotency_key = request.POST.get(
            "idempotency_key"
        )
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