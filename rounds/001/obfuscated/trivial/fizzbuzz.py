__import__('base64').b64decode(b'Rml6ekJ1enogd2l0aCBjb25maWd1cmFibGUgcnVsZXMu').decode()

def _ddd8536496ea(n: int, rules: dict | None=None) -> str:
    __import__('base64').b64decode(b'UmV0dXJuIEZpenpCdXp6IHN0cmluZyBmb3IgaW50ZWdlciBuIGdpdmVuIHJ1bGVzIGRpY3Qge2Rpdmlzb3I6IGxhYmVsfS4=').decode()
    if rules is None:
        rules = {3: __import__('base64').b64decode(b'Rml6eg==').decode(), 5: __import__('base64').b64decode(b'QnV6eg==').decode()}
    result = ''
    for divisor, label in sorted(rules.items()):
        if n % divisor == 0:
            result += label
    return result if result else str(n)

def _1beb7be514b8(limit: int) -> list[str]:
    __import__('base64').b64decode(b'UmV0dXJuIEZpenpCdXp6IHNlcXVlbmNlIGZyb20gMSB0byBsaW1pdCBpbmNsdXNpdmUu').decode()
    return [_ddd8536496ea(i) for i in range(1, limit + 1)]
if __name__ == __import__('base64').b64decode(b'X19tYWluX18=').decode():
    for line in _1beb7be514b8(20):
        print(line)