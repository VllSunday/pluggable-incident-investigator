def retry_delay(attempt: int, *, base: int = 1, maximum: int = 30) -> int:
    """Return an exponential retry delay capped at ``maximum`` seconds."""
    if attempt < 1:
        raise ValueError("attempt must be at least 1")
    return min(base * (2**attempt), maximum)

