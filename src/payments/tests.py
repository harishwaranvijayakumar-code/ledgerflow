from django.test import TestCase

from payments.models import IdempotencyRecord, Payment


class PaymentAPITests(TestCase):

    def test_creates_payment(self):
        response = self.client.post(
            "/api/payments/",
            data={
                "amount": "100.00",
                "currency": "USD",
            },
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="test-key-001",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(IdempotencyRecord.objects.count(), 1)

    def test_same_request_is_idempotent(self):
        payload = {
            "amount": "100.00",
            "currency": "USD",
        }

        first = self.client.post(
            "/api/payments/",
            data=payload,
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="test-key-002",
        )

        second = self.client.post(
            "/api/payments/",
            data=payload,
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="test-key-002",
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)

        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(IdempotencyRecord.objects.count(), 1)

        self.assertEqual(
            first.json()["payment"]["id"],
            second.json()["payment"]["id"],
        )

        self.assertTrue(second.json()["idempotent_replay"])

    def test_same_key_different_request_is_rejected(self):
        first = self.client.post(
            "/api/payments/",
            data={
                "amount": "100.00",
                "currency": "USD",
            },
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="test-key-003",
        )

        second = self.client.post(
            "/api/payments/",
            data={
                "amount": "500.00",
                "currency": "USD",
            },
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="test-key-003",
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)

        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(IdempotencyRecord.objects.count(), 1)

    def test_missing_idempotency_key_is_rejected(self):
        response = self.client.post(
            "/api/payments/",
            data={
                "amount": "100.00",
                "currency": "USD",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Payment.objects.count(), 0)

    def test_invalid_amount_is_rejected(self):
        response = self.client.post(
            "/api/payments/",
            data={
                "amount": "-10.00",
                "currency": "USD",
            },
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="test-key-004",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Payment.objects.count(), 0)