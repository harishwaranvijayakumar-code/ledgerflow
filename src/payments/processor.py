import uuid


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
    """
    Simulates an unreliable external payment processor.

    UNKNOWN deliberately means:
    the processor may have completed the operation, but LedgerFlow
    did not receive the response.
    """

    def __init__(self):
        self.operations = {}

    def execute(self, behavior="SUCCESS"):
        operation_id = str(uuid.uuid4())

        if behavior == "SUCCESS":
            self.operations[operation_id] = "SUCCESS"
            return operation_id, "SUCCESS"

        if behavior == "TRANSIENT_FAILURE":
            self.operations[operation_id] = "FAILED"
            raise TransientProcessorError("Temporary processor failure")

        if behavior == "PERMANENT_FAILURE":
            self.operations[operation_id] = "FAILED"
            raise PermanentProcessorError("Permanent processor rejection")

        if behavior == "UNKNOWN":
            self.operations[operation_id] = "SUCCESS"
            raise UnknownProcessorOutcome(operation_id)

        raise ValueError(f"Unknown processor behavior: {behavior}")

    def get_status(self, operation_id):
        return self.operations.get(operation_id)