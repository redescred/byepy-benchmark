def factorial(n):
    if n < 0:
        raise ValueError("factorial is undefined for negative numbers")
    if n == 0:
        return 1
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result


if __name__ == "__main__":
    for i in range(13):
        print(f"{i}! = {factorial(i)}")
