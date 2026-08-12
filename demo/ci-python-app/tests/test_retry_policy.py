import pytest

from retry_policy import retry_delay


@pytest.mark.parametrize(
    ("attempt", "expected"),
    [(1, 1), (2, 2), (3, 4), (6, 30)],
)
def test_retry_delay_uses_attempt_one_as_the_base(
    attempt: int, expected: int
) -> None:
    assert retry_delay(attempt, base=1, maximum=30) == expected


def test_retry_delay_rejects_invalid_attempt() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        retry_delay(0)

