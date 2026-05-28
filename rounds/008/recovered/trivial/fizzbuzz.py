def fizzbuzz_line(n, mapping=None):
    if mapping is None:
        mapping = {3: 'Fizz', 5: 'Buzz'}
    result = ''
    for divisor, word in sorted(mapping.items()):
        if n % divisor == 0:
            result = result + word
    if result:
        return result
    return str(n)


def fizzbuzz(n):
    return [fizzbuzz_line(i) for i in range(1, n + 1)]


if __name__ == '__main__':
    for line in fizzbuzz(20):
        print(line)
