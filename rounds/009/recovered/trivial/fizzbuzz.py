def fizzbuzz(n, mapping=None):
    if mapping is None:
        mapping = {3: 'Fizz', 5: 'Buzz'}
    result = ''
    for divisor, word in sorted(mapping.items()):
        if n % divisor == 0:
            result = result + word
    if result:
        return result
    return str(n)

def fizzbuzz_range(limit):
    return [fizzbuzz(i) for i in range(1, limit + 1)]
if __name__ == '__main__':
    for line in fizzbuzz_range(20):
        print(line)