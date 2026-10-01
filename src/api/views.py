import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from payments.models import Payment
from payments.services import (
    process_payment,
    reconcile_payment,
    retry_payment,
)

from .services import (
    IdempotencyConflict,
    InvalidPaymentRequest,
    create_or_get_payment,
    serialize_payment,
)


@csrf_exempt
def create_payment(request):
    if request.method != "POST":
        return JsonResponse(
            {"error": "Method not allowed"},
            status=405,
        )

    idempotency_key = request.headers.get("Idempotency-Key")

    if not idempotency_key:
        return JsonResponse(
            {"error": "Idempotency-Key header is required"},
            status=400,
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"error": "Invalid JSON"},
            status=400,
        )

    try:
        payment, created = create_or_get_payment(
            idempotency_key,
            data,
        )

        if created:
            process_payment(
                payment,
                data.get("processor_behavior", "SUCCESS"),
            )
            payment.refresh_from_db()

    except InvalidPaymentRequest as exc:
        return JsonResponse(
            {"error": str(exc)},
            status=400,
        )

    except IdempotencyConflict as exc:
        return JsonResponse(
            {"error": str(exc)},
            status=409,
        )

    return JsonResponse(
        {
            "payment": serialize_payment(payment),
            "idempotent_replay": not created,
        },
        status=201 if created else 200,
    )


@require_POST
def reconcile_payment_view(request, payment_id):
    payment = get_object_or_404(
        Payment,
        id=payment_id,
    )

    reconcile_payment(payment)

    return redirect(
        "payment-detail",
        payment_id=payment.id,
    )


@require_POST
def retry_payment_view(request, payment_id):
    payment = get_object_or_404(
        Payment,
        id=payment_id,
    )

    retry_payment(
        payment,
        behavior="SUCCESS",
    )

    return redirect(
        "payment-detail",
        payment_id=payment.id,
    )