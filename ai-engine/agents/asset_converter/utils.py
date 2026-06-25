"""
Asset Converter Agent - Utilities module.

Contains standalone utility functions.
"""


def is_power_of_2(n: int) -> bool:
    """Check if a number is a power of 2"""
    return n > 0 and (n & (n - 1)) == 0


def next_power_of_2(n: int) -> int:
    """Get the next power of 2 greater than or equal to n"""
    power = 1
    while power < n:
        power *= 2
    return power


def previous_power_of_2(n: int) -> int:
    """Get the previous power of 2 less than or equal to n"""
    if n <= 0:
        return 1
    power = 1
    while (power * 2) <= n:
        power *= 2
    return power
