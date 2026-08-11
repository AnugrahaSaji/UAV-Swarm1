"""Project-specific exception types for clearer error semantics."""

class ConfigError(NotImplementedError, ValueError):
    """Configuration validation errors (subclass of NotImplementedError for legacy callers)."""
    pass

class SequenceOverflow(Exception):
    """Sequence space exhausted or nearing exhaustion."""
    pass

class HandshakeError(Exception):
    """Handshake protocol level errors."""
    pass

class AeadError(Exception):
    """AEAD-related errors."""
    pass

class HandshakeFormatError(HandshakeError):
    pass

class HandshakeVerifyError(HandshakeError):
    pass
