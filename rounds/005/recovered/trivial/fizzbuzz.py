def fizzbuzz(n: int, rules: dict | None = None) -> str:
    if rules is None:
        rules = {3: 'Fizz', 5: 'Buzz'}
    result = ''
    for divisor, word in sorted(rules.items()):
        if n % divisor == 0:
            result += word
    return result if result else str(n)


def fizzbuzz_sequence(n: int) -> list[str]:
    return [fizzbuzz(i) for i in range(1, n + 1)]


if __name__ == '__main__':
    for line in fizzbuzz_sequence(20):
        print(line)
