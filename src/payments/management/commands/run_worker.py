import time

from django.core.management.base import BaseCommand

from payments.jobs import recover_expired_jobs
from payments.worker import process_next_job


class Command(BaseCommand):
    help = "Process queued LedgerFlow payment jobs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Process one available job and exit.",
        )

        parser.add_argument(
            "--poll",
            type=float,
            default=1.0,
            help="Seconds to wait between polling attempts.",
        )

        parser.add_argument(
            "--crash-after-claim",
            action="store_true",
            help="Simulate a worker crash immediately after claiming a job.",
        )

        parser.add_argument(
            "--crash-after-processor",
            action="store_true",
            help="Simulate a worker crash immediately after processor execution.",
        )

    def handle(self, *args, **options):
        once = options["once"]
        poll_interval = options["poll"]
        crash_after_claim = options["crash_after_claim"]
        crash_after_processor = options["crash_after_processor"]

        if crash_after_claim and crash_after_processor:
            raise ValueError(
                "Choose only one crash simulation mode."
            )

        self.stdout.write(
            self.style.SUCCESS(
                "LedgerFlow worker started."
            )
        )

        while True:
            recovered = recover_expired_jobs()

            for job in recovered:
                self.stdout.write(
                    self.style.WARNING(
                        f"Recovered expired job {job.id}."
                    )
                )

            job = process_next_job(
                crash_after_claim=crash_after_claim,
                crash_after_processor=crash_after_processor,
            )

            if job is not None:
                self.stdout.write(
                    f"Processed job {job.id} "
                    f"for payment {job.payment_id} "
                    f"with status {job.status}."
                )

            if once:
                if job is None and not recovered:
                    self.stdout.write(
                        "No queued jobs available."
                    )
                return

            time.sleep(poll_interval)