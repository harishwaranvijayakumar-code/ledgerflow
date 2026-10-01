from decimal import Decimal

from django.test import TestCase

from payments.models import Payment, PaymentAttempt

from .services import (
    IdempotencyConflict,
    create_or_get_payment,
)


class PaymentIdempotencyTests(TestCase):

    def test_first_request_creates_payment(self):
        payment, created = create_or_get_payment(
            "test-key-001",
            {
                "amount": "250.00",
                "currency": "USD",
            },
        )

        self.assertTrue(created)

        self.assertEqual(
            Payment.objects.count(),
            1,
        )

        payment.refresh_from_db()

        self.assertEqual(
            payment.amount,
            Decimal("250.00"),
        )

        self.assertEqual(
            payment.currency,
            "USD",
        )

    def test_same_key_and_same_request_replays_payment(self):
        first_payment, first_created = create_or_get_payment(
            "test-key-002",
            {
                "amount": "250.00",
                "currency": "USD",
            },
        )

        second_payment, second_created = create_or_get_payment(
            "test-key-002",
            {
                "amount": "250.00",
                "currency": "USD",
            },
        )

        self.assertTrue(first_created)
        self.assertFalse(second_created)

        self.assertEqual(
            first_payment.id,
            second_payment.id,
        )

        self.assertEqual(
            Payment.objects.count(),
            1,
        )

    def test_same_key_with_different_amount_is_rejected(self):
        create_or_get_payment(
            "test-key-003",
            {
                "amount": "250.00",
                "currency": "USD",
            },
        )

        with self.assertRaises(IdempotencyConflict):
            create_or_get_payment(
                "test-key-003",
                {
                    "amount": "300.00",
                    "currency": "USD",
                },
            )

        self.assertEqual(
            Payment.objects.count(),
            1,
        )

    def test_same_key_with_different_currency_is_rejected(self):
        create_or_get_payment(
            "test-key-004",
            {
                "amount": "250.00",
                "currency": "USD",
            },
        )

        with self.assertRaises(IdempotencyConflict):
            create_or_get_payment(
                "test-key-004",
                {
                    "amount": "250.00",
                    "currency": "EUR",
                },
            )

        self.assertEqual(
            Payment.objects.count(),
            1,
        )

    def test_simulator_behavior_is_not_part_of_request_identity(self):
        first_payment, first_created = create_or_get_payment(
            "test-key-005",
            {
                "amount": "250.00",
                "currency": "USD",
            },
        )

        second_payment, second_created = create_or_get_payment(
            "test-key-005",
            {
                "amount": "250.00",
                "currency": "USD",
                "processor_behavior": "TRANSIENT_FAILURE",
            },
        )

        self.assertTrue(first_created)
        self.assertFalse(second_created)

        self.assertEqual(
            first_payment.id,
            second_payment.id,
        )

        self.assertEqual(
            Payment.objects.count(),
            1,
        )

        self.assertEqual(
            PaymentAttempt.objects.count(),
            0,
        )