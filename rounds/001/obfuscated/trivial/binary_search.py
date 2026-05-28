__import__('base64').b64decode(b'QmluYXJ5IHNlYXJjaDogaXRlcmF0aXZlIGFuZCByZWN1cnNpdmUgdmFyaWFudHMu').decode()

def _cdd679b07636(arr: list, target) -> int:
    __import__('base64').b64decode(b'UmV0dXJuIGluZGV4IG9mIHRhcmdldCBpbiBzb3J0ZWQgYXJyLCBvciAtMSBpZiBub3QgZm91bmQu').decode()
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

def _3b8fbf78672f(arr: list, target, low: int=0, high: int=-1) -> int:
    __import__('base64').b64decode(b'UmVjdXJzaXZlIHZhcmlhbnQuIGhpZ2g9LTEgbWVhbnMgdXNlIGxlbihhcnIpLTEu').decode()
    if high == -1:
        high = len(arr) - 1
    if low > high:
        return -1
    mid = (low + high) // 2
    if arr[mid] == target:
        return mid
    elif arr[mid] < target:
        return _3b8fbf78672f(arr, target, mid + 1, high)
    else:
        return _3b8fbf78672f(arr, target, low, mid - 1)
if __name__ == __import__('base64').b64decode(b'X19tYWluX18=').decode():
    data = list(range(0, 100, 3))
    for t in [0, 15, 42, 99, 7]:
        idx = _cdd679b07636(data, t)
        print(f"search({t}) -> index {idx}, value {(data[idx] if idx >= 0 else 'not found')}")