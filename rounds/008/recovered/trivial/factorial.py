def factorial_recursive(n):
    if n == 0:
        return 1
    return n * factorial_recursive(n - 1)


def factorial_iterative(n):
    result = 1
    for i in range(2, n + 1):
        result = result * i
    return result


if __name__ == '__main__':
    for i in range(13):
        print(f'{i}! = {factorial_recursive(i)}')
