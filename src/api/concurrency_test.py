import threading

from django.db import connections
from django.test import TransactionTestCase

from payments.models import IdempotencyRecord, Payment

from .services import create_or_get_payment


class PaymentConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def test_concurrent_same_idempotency_key(self):
        worker_count = 10
        barrier = threading.Barrier(worker_count)

        results = []
        errors = []
        lock = threading.Lock()

        def create_payment():
            try:
                barrier.wait()

                payment, created = create_or_get_payment(
                    "concurrent-test-key",
                    {
                        "amount": "250.00",
                        "currency": "USD",
                    },
                )

                with lock:
                    results.append(
                        {
                            "payment_id": payment.id,
                            "created": created,
                        }
                    )

            except Exception as exc:
                with lock:
                    errors.append(exc)

            finally:
                # Each worker thread gets its own Django database
                # connection. Close it so PostgreSQL can tear down
                # the temporary test database cleanly.
                connections.close_all()

        threads = [
            threading.Thread(target=create_payment)
            for _ in range(worker_count)
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        self.assertEqual(
            len(errors),
            0,
            f"Concurrent request errors: {errors}",
        )

        self.assertEqual(len(results), worker_count)

        self.assertEqual(
            Payment.objects.count(),
            1,
            "Concurrent requests created more than one Payment.",
        )

        self.assertEqual(
            IdempotencyRecord.objects.count(),
            1,
            "Concurrent requests created more than one IdempotencyRecord.",
        )

        payment_ids = {
            result["payment_id"]
            for result in results
        }

        self.assertEqual(
            len(payment_ids),
            1,
            "Concurrent requests did not resolve to the same Payment.",
        )

        created_count = sum(
            result["created"]
            for result in results
        )

        self.assertEqual(
            created_count,
            1,
            "Exactly one concurrent request must create the Payment.",
        )