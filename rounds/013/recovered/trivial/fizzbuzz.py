def fizzbuzz(n, rules=None):
    if rules is None:
        rules = {3: 'Fizz', 5: 'Buzz'}
    result = ''
    for divisor, word in sorted(rules.items()):
        if n % divisor == 0:
            result = result + word
    return result if result else str(n)

def fizzbuzz_range(limit):
    return [fizzbuzz(i) for i in range(1, limit + 1)]
if __name__ == '__main__':
    for line in fizzbuzz_range(20):
        print(line)
