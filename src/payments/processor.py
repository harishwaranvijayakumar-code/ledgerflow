import uuid

from .models import ProcessorOperation


class ProcessorError(Exception):
    pass


class TransientProcessorError(ProcessorError):
    pass


class PermanentProcessorError(ProcessorError):
    pass


class UnknownProcessorOutcome(ProcessorError):
    def __init__(self, operation_id):
        self.operation_id = operation_id
        super().__init__("Processor outcome is unknown")


class ProcessorSimulator:
    def execute(
        self,
        behavior="SUCCESS",
        operation_id=None,
    ):
        if operation_id is None:
            operation_id = str(uuid.uuid4())

        existing = ProcessorOperation.objects.filter(
            operation_id=operation_id
        ).first()

        if existing is not None:
            if existing.outcome == ProcessorOperation.Outcome.SUCCESS:
                return operation_id, "SUCCESS"

            return operation_id, "FAILED"

        if behavior == "SUCCESS":
            ProcessorOperation.objects.create(
                operation_id=operation_id,
                outcome=ProcessorOperation.Outcome.SUCCESS,
            )

            return operation_id, "SUCCESS"

        if behavior == "TRANSIENT_FAILURE":
            ProcessorOperation.objects.create(
                operation_id=operation_id,
                outcome=ProcessorOperation.Outcome.FAILED,
            )

            raise TransientProcessorError(
                "Temporary processor failure"
            )

        if behavior == "PERMANENT_FAILURE":
            ProcessorOperation.objects.create(
                operation_id=operation_id,
                outcome=ProcessorOperation.Outcome.FAILED,
            )

            raise PermanentProcessorError(
                "Permanent processor rejection"
            )

        if behavior == "UNKNOWN":
            ProcessorOperation.objects.create(
                operation_id=operation_id,
                outcome=ProcessorOperation.Outcome.SUCCESS,
            )

            raise UnknownProcessorOutcome(
                operation_id
            )

        raise ValueError(
            f"Unknown processor behavior: {behavior}"
        )

    def get_status(self, operation_id):
        operation = (
            ProcessorOperation.objects
            .filter(operation_id=operation_id)
            .first()
        )

        if operation is None:
            return None

        return operation.outcome