def binary_search(arr, target):
    right = len(arr) - 1
    left = 0
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        if arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1

def binary_search_recursive(arr, target, low=0, high=-1):
    if high == -1:
        high = len(arr) - 1
    if low > high:
        return -1
    mid = (low + high) // 2
    if arr[mid] == target:
        return mid
    if arr[mid] < target:
        return binary_search_recursive(arr, target, mid + 1, high)
    return binary_search_recursive(arr, target, low, mid - 1)
if __name__ == '__main__':
    data = list(range(0, 100, 3))
    for t in (0, 15, 42, 99, 7):
        idx = binary_search(data, t)
        print(f"search({t}) -> index {idx}, value {(data[idx] if idx >= 0 else 'not found')}")