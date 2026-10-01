import hashlib
import json
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction

from payments.models import IdempotencyRecord, Payment


class InvalidPaymentRequest(Exception):
    pass


class IdempotencyConflict(Exception):
    pass


def normalize_payment_request(data):
    amount = data.get("amount")
    currency = data.get("currency")

    if amount is None or currency is None:
        raise InvalidPaymentRequest("amount and currency are required")

    try:
        amount = Decimal(str(amount))
    except (InvalidOperation, ValueError):
        raise InvalidPaymentRequest("amount must be a valid number")

    if amount <= 0:
        raise InvalidPaymentRequest("amount must be greater than zero")

    currency = str(currency).upper()

    if len(currency) != 3 or not currency.isalpha():
        raise InvalidPaymentRequest("currency must be a 3-letter code")

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

    return hashlib.sha256(canonical.encode()).hexdigest()


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
                "Idempotency-Key was already used with different request data"
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
                "Idempotency-Key was already used with different request data"
            )

        return existing.payment, False