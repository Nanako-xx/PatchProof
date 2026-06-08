class PatchProofError(Exception):
    """Base error for PatchProof."""


class CommandValidationError(PatchProofError):
    """Raised when a user-provided command is outside the safe allowlist."""


class LLMProviderError(PatchProofError):
    """Raised when an LLM provider call fails or returns invalid data."""


class PatchSafetyError(PatchProofError):
    """Raised when a patch violates deterministic safety rules."""
