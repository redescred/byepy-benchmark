"""Binary search: iterative and recursive variants."""


def binary_search_iterative(arr: list, target) -> int:
    """Return index of target in sorted arr, or -1 if not found."""
    low, high = (0, len(arr) - 1)
    while low <= high:
        mid = (low + high) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1


def binary_search_recursive(arr: list, target, low: int = 0, high: int = -1) -> int:
    """Recursive variant. high=-1 means use len(arr)-1."""
    if high == -1:
        high = len(arr) - 1
    if low > high:
        return -1
    mid = (low + high) // 2
    if arr[mid] == target:
        return mid
    elif arr[mid] < target:
        return binary_search_recursive(arr, target, mid + 1, high)
    else:
        return binary_search_recursive(arr, target, low, mid - 1)


if __name__ == '__main__':
    data = list(range(0, 100, 3))
    for t in [0, 15, 42, 99, 7]:
        idx = binary_search_iterative(data, t)
        print(f"search({t}) -> index {idx}, value {(data[idx] if idx >= 0 else 'not found')}")
