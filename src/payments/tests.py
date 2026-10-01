from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from .jobs import (
    claim_next_job,
    enqueue_payment,
    recover_expired_jobs,
)
from .models import (
    Payment,
    PaymentAttempt,
    PaymentJob,
    ProcessorOperation,
)
from .services import (
    process_payment,
    reconcile_payment,
    retry_payment,
)
from .worker import process_next_job


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
                payment=payment,
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
                payment=payment,
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
                payment=payment,
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
                payment=payment,
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

    def test_enqueue_payment_creates_one_job(self):
        payment = self.create_payment()

        job, created = enqueue_payment(
            payment,
            processor_behavior="SUCCESS",
        )

        self.assertTrue(created)

        self.assertEqual(
            job.payment_id,
            payment.id,
        )

        self.assertEqual(
            job.status,
            PaymentJob.Status.QUEUED,
        )

        self.assertEqual(
            PaymentJob.objects.count(),
            1,
        )

    def test_enqueue_payment_is_idempotent(self):
        payment = self.create_payment()

        first_job, first_created = enqueue_payment(
            payment,
            processor_behavior="SUCCESS",
        )

        second_job, second_created = enqueue_payment(
            payment,
            processor_behavior="SUCCESS",
        )

        self.assertTrue(first_created)

        self.assertFalse(second_created)

        self.assertEqual(
            first_job.id,
            second_job.id,
        )

        self.assertEqual(
            PaymentJob.objects.count(),
            1,
        )

    def test_claim_next_job_moves_job_to_processing(self):
        payment = self.create_payment()

        job, _ = enqueue_payment(payment)

        claimed_job = claim_next_job()

        job.refresh_from_db()

        self.assertIsNotNone(
            claimed_job,
        )

        self.assertEqual(
            claimed_job.id,
            job.id,
        )

        self.assertEqual(
            job.status,
            PaymentJob.Status.PROCESSING,
        )

        self.assertEqual(
            job.attempts,
            1,
        )

        self.assertIsNotNone(
            job.started_at,
        )

    def test_worker_processes_successful_job(self):
        payment = self.create_payment()

        job, _ = enqueue_payment(
            payment,
            processor_behavior="SUCCESS",
        )

        processed_job = process_next_job()

        payment.refresh_from_db()
        job.refresh_from_db()

        self.assertEqual(
            processed_job.id,
            job.id,
        )

        self.assertEqual(
            job.status,
            PaymentJob.Status.COMPLETED,
        )

        self.assertEqual(
            payment.status,
            Payment.Status.SUCCEEDED,
        )

        self.assertEqual(
            PaymentAttempt.objects.filter(
                payment=payment,
            ).count(),
            1,
        )

    def test_worker_unknown_outcome_preserves_uncertainty(self):
        payment = self.create_payment()

        job, _ = enqueue_payment(
            payment,
            processor_behavior="UNKNOWN",
        )

        process_next_job()

        payment.refresh_from_db()
        job.refresh_from_db()

        attempt = PaymentAttempt.objects.get(
            payment=payment,
        )

        self.assertEqual(
            job.status,
            PaymentJob.Status.FAILED,
        )

        self.assertEqual(
            payment.status,
            Payment.Status.PROCESSING,
        )

        self.assertEqual(
            attempt.status,
            PaymentAttempt.Status.UNKNOWN,
        )

    def test_worker_transient_failure_keeps_payment_processing(self):
        payment = self.create_payment()

        job, _ = enqueue_payment(
            payment,
            processor_behavior="TRANSIENT_FAILURE",
        )

        process_next_job()

        payment.refresh_from_db()
        job.refresh_from_db()

        attempt = PaymentAttempt.objects.get(
            payment=payment,
        )

        self.assertEqual(
            job.status,
            PaymentJob.Status.QUEUED,
        )

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

    def test_claimed_job_gets_lease(self):
        payment = self.create_payment()

        job, _ = enqueue_payment(payment)

        claimed_job = claim_next_job()

        claimed_job.refresh_from_db()

        self.assertEqual(
            claimed_job.id,
            job.id,
        )

        self.assertEqual(
            claimed_job.status,
            PaymentJob.Status.PROCESSING,
        )

        self.assertIsNotNone(
            claimed_job.lease_expires_at,
        )

    def test_expired_processing_job_is_requeued(self):
        payment = self.create_payment()

        job, _ = enqueue_payment(payment)

        claim_next_job()

        job.refresh_from_db()

        job.lease_expires_at = (
            timezone.now() - timedelta(seconds=1)
        )

        job.save(
            update_fields=[
                "lease_expires_at",
            ]
        )

        recovered = recover_expired_jobs()

        job.refresh_from_db()

        self.assertEqual(
            len(recovered),
            1,
        )

        self.assertEqual(
            recovered[0].id,
            job.id,
        )

        self.assertEqual(
            job.status,
            PaymentJob.Status.QUEUED,
        )

        self.assertIsNone(
            job.lease_expires_at,
        )

    def test_recovered_job_reuses_processor_operation(self):
        payment = self.create_payment()

        job, _ = enqueue_payment(
            payment,
            processor_behavior="SUCCESS",
        )

        claimed_job = claim_next_job()

        claimed_job.processor_operation_id = (
            "recovery-operation-001"
        )

        claimed_job.save(
            update_fields=[
                "processor_operation_id",
            ]
        )

        claimed_job.lease_expires_at = (
            timezone.now() - timedelta(seconds=1)
        )

        claimed_job.save(
            update_fields=[
                "lease_expires_at",
            ]
        )

        recover_expired_jobs()

        processed_job = process_next_job()

        payment.refresh_from_db()
        processed_job.refresh_from_db()

        self.assertEqual(
            payment.status,
            Payment.Status.SUCCEEDED,
        )

        self.assertEqual(
            processed_job.status,
            PaymentJob.Status.COMPLETED,
        )

        self.assertEqual(
            processed_job.processor_operation_id,
            "recovery-operation-001",
        )

        self.assertEqual(
            PaymentAttempt.objects.filter(
                payment=payment,
            ).count(),
            1,
        )

        self.assertEqual(
            ProcessorOperation.objects.filter(
                operation_id="recovery-operation-001",
            ).count(),
            1,
        )

    def test_worker_crash_after_claim_leaves_job_processing(self):
        payment = self.create_payment()
        job, _ = enqueue_payment(
            payment,
            processor_behavior="SUCCESS",
        )

        with self.assertRaises(RuntimeError):
            process_next_job(
                crash_after_claim=True,
            )

        job.refresh_from_db()
        payment.refresh_from_db()

        self.assertEqual(
            job.status,
            PaymentJob.Status.PROCESSING,
        )
        self.assertIsNotNone(job.lease_expires_at)
        self.assertTrue(job.processor_operation_id)
        self.assertEqual(
            payment.status,
            Payment.Status.CREATED,
        )
        self.assertEqual(
            PaymentAttempt.objects.filter(
                payment=payment
            ).count(),
            0,
        )

    def test_worker_crash_after_processor_can_be_recovered(self):
        payment = self.create_payment()
        job, _ = enqueue_payment(
            payment,
            processor_behavior="SUCCESS",
        )

        with self.assertRaises(RuntimeError):
            process_next_job(
                crash_after_processor=True,
            )

        job.refresh_from_db()
        payment.refresh_from_db()

        self.assertEqual(
            job.status,
            PaymentJob.Status.PROCESSING,
        )
        self.assertTrue(job.processor_operation_id)
        self.assertEqual(
            payment.status,
            Payment.Status.PROCESSING,
        )

        operation_id = job.processor_operation_id

        self.assertEqual(
            ProcessorOperation.objects.filter(
                operation_id=operation_id
            ).count(),
            1,
        )

        self.assertEqual(
            PaymentAttempt.objects.filter(
                payment=payment
            ).count(),
            0,
        )

        job.lease_expires_at = (
            timezone.now() - timedelta(seconds=1)
        )
        job.save(
            update_fields=["lease_expires_at"]
        )

        recovered = recover_expired_jobs()

        self.assertEqual(len(recovered), 1)

        processed_job = process_next_job()

        payment.refresh_from_db()
        processed_job.refresh_from_db()

        self.assertEqual(
            payment.status,
            Payment.Status.SUCCEEDED,
        )
        self.assertEqual(
            processed_job.status,
            PaymentJob.Status.COMPLETED,
        )
        self.assertEqual(
            processed_job.processor_operation_id,
            operation_id,
        )

        self.assertEqual(
            ProcessorOperation.objects.filter(
                operation_id=operation_id
            ).count(),
            1,
        )

        self.assertEqual(
            PaymentAttempt.objects.filter(
                payment=payment
            ).count(),
            1,
        )

        attempt = PaymentAttempt.objects.get(
            payment=payment
        )

        self.assertEqual(
            attempt.processor_operation_id,
            operation_id,
        )
        self.assertEqual(
            attempt.status,
            PaymentAttempt.Status.SUCCESS,
        )