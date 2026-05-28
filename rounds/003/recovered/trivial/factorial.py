def factorial(n: int) -> int:
    if n < 0:
        raise ValueError("factorial is undefined for negative numbers")
    if n == 0:
        return 1
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result


def factorial_recursive(n: int) -> int:
    if n < 0:
        raise ValueError("factorial is undefined for negative numbers")
    if n == 0:
        return 1
    return n * factorial_recursive(n - 1)


if __name__ == "__main__":
    for i in range(13):
        print(f"{i}! = {factorial(i)}")
