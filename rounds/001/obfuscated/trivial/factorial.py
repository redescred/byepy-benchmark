__import__('base64').b64decode(b'UmVjdXJzaXZlIGZhY3RvcmlhbCB3aXRoIG1lbW9pc2F0aW9uLg==').decode()

def _317c9d64dfda(n: int) -> int:
    __import__('base64').b64decode(b'UmV0dXJuIG4hIGZvciBub24tbmVnYXRpdmUgaW50ZWdlciBuLg==').decode()
    if n < 0:
        raise ValueError(__import__('base64').b64decode(b'ZmFjdG9yaWFsIGlzIHVuZGVmaW5lZCBmb3IgbmVnYXRpdmUgbnVtYmVycw==').decode())
    if n == 0:
        return 1
    return n * _317c9d64dfda(n - 1)

def _fef0c09b6617(n: int) -> int:
    __import__('base64').b64decode(b'SXRlcmF0aXZlIHZlcnNpb24gZm9yIGNvbXBhcmlzb24u').decode()
    if n < 0:
        raise ValueError(__import__('base64').b64decode(b'ZmFjdG9yaWFsIGlzIHVuZGVmaW5lZCBmb3IgbmVnYXRpdmUgbnVtYmVycw==').decode())
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result
if __name__ == __import__('base64').b64decode(b'X19tYWluX18=').decode():
    for i in range(13):
        print(f'{i}! = {_317c9d64dfda(i)}')