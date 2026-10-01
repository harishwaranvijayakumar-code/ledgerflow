from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from .jobs import (
    MAX_JOB_ATTEMPTS,
    calculate_retry_delay,
    enqueue_payment,
    recover_expired_jobs,
)
from .models import (
    Payment,
    PaymentAttempt,
    PaymentJob,
    ProcessorOperation,
)
from .services import reconcile_payment
from .worker import process_next_job


class RetryAndReconciliationTests(TestCase):

    def create_payment(self):
        return Payment.objects.create(
            amount="250.00",
            currency="USD",
            status=Payment.Status.CREATED,
        )

    def test_retry_delay_uses_exponential_backoff(self):
        self.assertEqual(
            calculate_retry_delay(1),
            5,
        )

        self.assertEqual(
            calculate_retry_delay(2),
            10,
        )

        self.assertEqual(
            calculate_retry_delay(3),
            20,
        )

    def test_transient_failure_is_requeued(self):
        payment = self.create_payment()

        job, _ = enqueue_payment(
            payment,
            processor_behavior="TRANSIENT_FAILURE",
        )

        before = timezone.now()

        process_next_job()

        job.refresh_from_db()
        payment.refresh_from_db()

        self.assertEqual(
            job.status,
            PaymentJob.Status.QUEUED,
        )

        self.assertEqual(
            job.attempts,
            1,
        )

        self.assertEqual(
            payment.status,
            Payment.Status.PROCESSING,
        )

        self.assertGreater(
            job.available_at,
            before,
        )

        attempt = PaymentAttempt.objects.get(
            payment=payment
        )

        self.assertEqual(
            attempt.status,
            PaymentAttempt.Status.FAILED,
        )

        self.assertEqual(
            attempt.failure_type,
            "TRANSIENT",
        )

        self.assertTrue(
            attempt.processor_operation_id
        )

        self.assertEqual(
            job.processor_operation_id,
            "",
        )

    def test_transient_retry_creates_new_processor_operation(self):
        payment = self.create_payment()

        job, _ = enqueue_payment(
            payment,
            processor_behavior="TRANSIENT_FAILURE",
        )

        process_next_job()

        first_attempt = (
            PaymentAttempt.objects
            .get(payment=payment)
        )

        first_operation = (
            first_attempt.processor_operation_id
        )

        job.refresh_from_db()

        job.available_at = timezone.now()
        job.processor_behavior = "SUCCESS"

        job.save(
            update_fields=[
                "available_at",
                "processor_behavior",
            ]
        )

        process_next_job()

        payment.refresh_from_db()
        job.refresh_from_db()

        attempts = list(
            PaymentAttempt.objects
            .filter(payment=payment)
            .order_by("created_at")
        )

        self.assertEqual(
            len(attempts),
            2,
        )

        self.assertEqual(
            attempts[0].failure_type,
            "TRANSIENT",
        )

        self.assertEqual(
            attempts[1].status,
            PaymentAttempt.Status.SUCCESS,
        )

        self.assertNotEqual(
            attempts[0].processor_operation_id,
            attempts[1].processor_operation_id,
        )

        self.assertEqual(
            payment.status,
            Payment.Status.SUCCEEDED,
        )

        self.assertEqual(
            job.status,
            PaymentJob.Status.COMPLETED,
        )

        self.assertEqual(
            ProcessorOperation.objects.count(),
            2,
        )

    def test_transient_failures_stop_after_max_attempts(self):
        payment = self.create_payment()

        job, _ = enqueue_payment(
            payment,
            processor_behavior="TRANSIENT_FAILURE",
        )

        for attempt_number in range(MAX_JOB_ATTEMPTS):
            process_next_job()

            job.refresh_from_db()

            if (
                job.status
                == PaymentJob.Status.QUEUED
            ):
                job.available_at = timezone.now()

                job.save(
                    update_fields=[
                        "available_at",
                    ]
                )

        payment.refresh_from_db()
        job.refresh_from_db()

        self.assertEqual(
            job.attempts,
            MAX_JOB_ATTEMPTS,
        )

        self.assertEqual(
            job.status,
            PaymentJob.Status.FAILED,
        )

        self.assertEqual(
            payment.status,
            Payment.Status.FAILED,
        )

        self.assertEqual(
            PaymentAttempt.objects.filter(
                payment=payment
            ).count(),
            MAX_JOB_ATTEMPTS,
        )

    def test_permanent_failure_is_not_requeued(self):
        payment = self.create_payment()

        job, _ = enqueue_payment(
            payment,
            processor_behavior="PERMANENT_FAILURE",
        )

        process_next_job()

        payment.refresh_from_db()
        job.refresh_from_db()

        self.assertEqual(
            payment.status,
            Payment.Status.FAILED,
        )

        self.assertEqual(
            job.status,
            PaymentJob.Status.FAILED,
        )

        self.assertEqual(
            job.attempts,
            1,
        )

        self.assertEqual(
            PaymentAttempt.objects.filter(
                payment=payment
            ).count(),
            1,
        )

    def test_unknown_outcome_is_not_retried(self):
        payment = self.create_payment()

        job, _ = enqueue_payment(
            payment,
            processor_behavior="UNKNOWN",
        )

        process_next_job()

        payment.refresh_from_db()
        job.refresh_from_db()

        attempt = PaymentAttempt.objects.get(
            payment=payment
        )

        self.assertEqual(
            payment.status,
            Payment.Status.PROCESSING,
        )

        self.assertEqual(
            job.status,
            PaymentJob.Status.FAILED,
        )

        self.assertEqual(
            attempt.status,
            PaymentAttempt.Status.UNKNOWN,
        )

        self.assertTrue(
            attempt.processor_operation_id
        )

    def test_reconciliation_resolves_unknown_without_new_operation(
        self,
    ):
        payment = self.create_payment()

        job, _ = enqueue_payment(
            payment,
            processor_behavior="UNKNOWN",
        )

        process_next_job()

        payment.refresh_from_db()
        job.refresh_from_db()

        attempt = PaymentAttempt.objects.get(
            payment=payment
        )

        operation_id = (
            attempt.processor_operation_id
        )

        processor_count_before = (
            ProcessorOperation.objects
            .filter(
                operation_id=operation_id
            )
            .count()
        )

        self.assertEqual(
            processor_count_before,
            1,
        )

        resolved = reconcile_payment(
            payment
        )

        self.assertIsNotNone(resolved)

        payment.refresh_from_db()
        job.refresh_from_db()
        attempt.refresh_from_db()

        self.assertEqual(
            attempt.status,
            PaymentAttempt.Status.SUCCESS,
        )

        self.assertEqual(
            attempt.processor_operation_id,
            operation_id,
        )

        self.assertEqual(
            payment.status,
            Payment.Status.SUCCEEDED,
        )

        self.assertEqual(
            job.status,
            PaymentJob.Status.COMPLETED,
        )

        self.assertEqual(
            ProcessorOperation.objects
            .filter(
                operation_id=operation_id
            )
            .count(),
            1,
        )

        self.assertEqual(
            PaymentAttempt.objects.filter(
                payment=payment
            ).count(),
            1,
        )

    def test_reconciliation_does_nothing_when_processor_unknown(
        self,
    ):
        payment = self.create_payment()

        attempt = PaymentAttempt.objects.create(
            payment=payment,
            processor_operation_id="missing-operation",
            status=PaymentAttempt.Status.UNKNOWN,
            failure_type="",
        )

        result = reconcile_payment(
            payment
        )

        self.assertIsNone(result)

        attempt.refresh_from_db()

        self.assertEqual(
            attempt.status,
            PaymentAttempt.Status.UNKNOWN,
        )

        payment.refresh_from_db()

        self.assertEqual(
            payment.status,
            Payment.Status.CREATED,
        )

    def test_expired_job_recovery_preserves_processor_operation(
        self,
    ):
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

        operation_id = (
            job.processor_operation_id
        )

        self.assertTrue(operation_id)

        self.assertEqual(
            job.status,
            PaymentJob.Status.PROCESSING,
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
            0,
        )

        job.lease_expires_at = (
            timezone.now()
            - timedelta(seconds=1)
        )

        job.save(
            update_fields=[
                "lease_expires_at",
            ]
        )

        recovered = recover_expired_jobs()

        self.assertEqual(
            len(recovered),
            1,
        )

        job.refresh_from_db()

        self.assertEqual(
            job.status,
            PaymentJob.Status.QUEUED,
        )

        self.assertEqual(
            job.processor_operation_id,
            operation_id,
        )

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