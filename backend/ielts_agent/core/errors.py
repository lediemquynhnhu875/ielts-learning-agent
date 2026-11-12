"""Shared error types independent of any provider or database driver."""


class ProviderError(RuntimeError):
    """Sanitized upstream failure without raw HTTP bodies or credentials."""


class InvalidAgentOutput(RuntimeError):
    """Retryable malformed model output."""


class DuplicateError(ValueError):
    def __init__(self, similarity: float, item_id: str):
        self.similarity = similarity
        self.item_id = item_id
        super().__init__(f"Duplicate content: similarity={similarity:.6f}, item_id={item_id}")
