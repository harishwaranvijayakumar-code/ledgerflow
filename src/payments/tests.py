from django.test import TestCase

from .models import Payment, PaymentAttempt, ProcessorOperation
from .services import (
    process_payment,
    reconcile_payment,
    retry_payment,
)


class PaymentProcessingTests(TestCase):

    def create_payment(self, payment_id="test-payment-001"):
        return Payment.objects.create(
            amount="250.00",
            currency="USD",
            status=Payment.Status.CREATED,
        )

    def test_transient_failure_keeps_payment_processing(self):
        payment = self.create_payment()

        attempt = process_payment(
            payment,
            behavior="TRANSIENT_FAILURE",
        )

        payment.refresh_from_db()

        self.assertEqual(
            payment.status,
            Payment.Status.PROCESSING,
        )

        self.assertEqual(
            attempt.status,
            PaymentAttempt.Status.FAILED,
        )

        self.assertEqual(
            attempt.failure_type,
            "TRANSIENT",
        )

        self.assertEqual(
            attempt.error,
            "Temporary processor failure",
        )

        self.assertEqual(
            PaymentAttempt.objects.filter(
                payment=payment
            ).count(),
            1,
        )

    def test_permanent_failure_marks_payment_failed(self):
        payment = self.create_payment(
            "test-payment-002",
        )

        attempt = process_payment(
            payment,
            behavior="PERMANENT_FAILURE",
        )

        payment.refresh_from_db()

        self.assertEqual(
            payment.status,
            Payment.Status.FAILED,
        )

        self.assertEqual(
            attempt.status,
            PaymentAttempt.Status.FAILED,
        )

        self.assertEqual(
            attempt.failure_type,
            "PERMANENT",
        )

        self.assertEqual(
            attempt.error,
            "Permanent processor rejection",
        )

    def test_transient_failure_can_be_retried(self):
        payment = self.create_payment(
            "test-payment-003",
        )

        first_attempt = process_payment(
            payment,
            behavior="TRANSIENT_FAILURE",
        )

        retry_attempt = retry_payment(
            payment,
            behavior="SUCCESS",
        )

        payment.refresh_from_db()

        self.assertEqual(
            first_attempt.status,
            PaymentAttempt.Status.FAILED,
        )

        self.assertEqual(
            first_attempt.failure_type,
            "TRANSIENT",
        )

        self.assertEqual(
            retry_attempt.status,
            PaymentAttempt.Status.SUCCESS,
        )

        self.assertEqual(
            payment.status,
            Payment.Status.SUCCEEDED,
        )

        self.assertEqual(
            PaymentAttempt.objects.filter(
                payment=payment
            ).count(),
            2,
        )

    def test_retry_does_not_create_second_payment(self):
        payment = self.create_payment(
            "test-payment-004",
        )

        process_payment(
            payment,
            behavior="TRANSIENT_FAILURE",
        )

        retry_payment(
            payment,
            behavior="SUCCESS",
        )

        self.assertEqual(
            Payment.objects.count(),
            1,
        )

        self.assertEqual(
            PaymentAttempt.objects.filter(
                payment=payment
            ).count(),
            2,
        )

    def test_unknown_outcome_keeps_payment_processing(self):
        payment = self.create_payment(
            "test-payment-005",
        )

        attempt = process_payment(
            payment,
            behavior="UNKNOWN",
        )

        payment.refresh_from_db()

        self.assertEqual(
            payment.status,
            Payment.Status.PROCESSING,
        )

        self.assertEqual(
            attempt.status,
            PaymentAttempt.Status.UNKNOWN,
        )

        self.assertTrue(
            attempt.processor_operation_id,
        )

        self.assertEqual(
            PaymentAttempt.objects.filter(
                payment=payment
            ).count(),
            1,
        )

    def test_reconciliation_resolves_unknown_success(self):
        payment = self.create_payment(
            "test-payment-006",
        )

        unknown_attempt = process_payment(
            payment,
            behavior="UNKNOWN",
        )

        resolved_attempt = reconcile_payment(
            payment,
        )

        payment.refresh_from_db()
        unknown_attempt.refresh_from_db()

        self.assertIsNotNone(
            resolved_attempt,
        )

        self.assertEqual(
            unknown_attempt.status,
            PaymentAttempt.Status.SUCCESS,
        )

        self.assertEqual(
            payment.status,
            Payment.Status.SUCCEEDED,
        )

        self.assertEqual(
            unknown_attempt.completed_at is not None,
            True,
        )

    def test_reconciliation_does_not_create_new_processor_operation(self):
        payment = self.create_payment(
            "test-payment-007",
        )

        unknown_attempt = process_payment(
            payment,
            behavior="UNKNOWN",
        )

        original_operation_id = (
            unknown_attempt.processor_operation_id
        )

        operation_count_before = (
            ProcessorOperation.objects.count()
        )

        reconcile_payment(payment)

        operation_count_after = (
            ProcessorOperation.objects.count()
        )

        unknown_attempt.refresh_from_db()

        self.assertEqual(
            operation_count_before,
            operation_count_after,
        )

        self.assertEqual(
            unknown_attempt.processor_operation_id,
            original_operation_id,
        )

        self.assertEqual(
            unknown_attempt.status,
            PaymentAttempt.Status.SUCCESS,
        )