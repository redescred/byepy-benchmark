def binary_search(arr, target):
    lo, hi = 0, len(arr) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if arr[mid] == target:
            return mid
        if arr[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1


def binary_search_recursive(arr, target, lo=0, hi=-1):
    if hi == -1:
        hi = len(arr) - 1
    if lo > hi:
        return -1
    mid = (lo + hi) // 2
    if arr[mid] == target:
        return mid
    if arr[mid] < target:
        return binary_search_recursive(arr, target, mid + 1, hi)
    return binary_search_recursive(arr, target, lo, mid - 1)


if __name__ == '__main__':
    data = list(range(0, 100, 3))
    for t in (0, 15, 42, 99, 7):
        idx = binary_search(data, t)
        print(f"search({t}) -> index {idx}, value {data[idx] if idx >= 0 else 'not found'}")
