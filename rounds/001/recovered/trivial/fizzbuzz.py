"""FizzBuzz with configurable rules."""


def fizzbuzz(n: int, rules: dict | None = None) -> str:
    """Return FizzBuzz string for integer n given rules dict {divisor: label}."""
    if rules is None:
        rules = {3: 'Fizz', 5: 'Buzz'}
    result = ''
    for divisor, label in sorted(rules.items()):
        if n % divisor == 0:
            result += label
    return result if result else str(n)


def fizzbuzz_sequence(limit: int) -> list[str]:
    """Return FizzBuzz sequence from 1 to limit inclusive."""
    return [fizzbuzz(i) for i in range(1, limit + 1)]


if __name__ == '__main__':
    for line in fizzbuzz_sequence(20):
        print(line)
