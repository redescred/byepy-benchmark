def fizzbuzz_value(n, mapping=None):
    if mapping is None:
        mapping = {3: 'Fizz', 5: 'Buzz'}
    result = ''
    for divisor, label in sorted(mapping.items()):
        if n % divisor == 0:
            result += label
    if result:
        return result
    return str(n)


def fizzbuzz_lines(n):
    return [fizzbuzz_value(i) for i in range(1, n + 1)]


if __name__ == '__main__':
    for line in fizzbuzz_lines(20):
        print(line)
