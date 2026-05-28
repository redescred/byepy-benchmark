__import__('base64').b64decode(b'RW50cnkgcG9pbnQ6IHB5dGhvbiAtbSBjc3ZraXQ=').decode()
from .formatter import CSVFormatter, TableFormatter
from .parser import CSVParser
SAMPLE = __import__('base64').b64decode(b'bmFtZSxhZ2UsY2l0eSxhY3RpdmUKQWxpY2UsMzAsTG9uZG9uLHRydWUKQm9iLDI1LE1hbmNoZXN0ZXIsZmFsc2UKQ2Fyb2wsMzUsTG9uZG9uLHRydWUKRGF2ZSwyOCxFZGluYnVyZ2gsdHJ1ZQo=').decode()

def _f56cda8694e7() -> None:
    parser = CSVParser().parse(SAMPLE)
    records = parser.dicts()
    print(__import__('base64').b64decode(b'PT09IENTViByb3VuZC10cmlwID09PQ==').decode())
    print(CSVFormatter().format_dicts(records))
    print(__import__('base64').b64decode(b'PT09IFRhYmxlID09PQ==').decode())
    print(TableFormatter().format_dicts(records))
    print(__import__('base64').b64decode(b'PT09IExvbmRvbiwgc29ydGVkIGJ5IGFnZSA9PT0=').decode())
    london = parser.filter_rows(lambda r: r[__import__('base64').b64decode(b'Y2l0eQ==').decode()] == __import__('base64').b64decode(b'TG9uZG9u').decode()).sort_by(__import__('base64').b64decode(b'YWdl').decode())
    print(TableFormatter().format_dicts(london.dicts()))
    print(f'Total rows: {len(parser)}')
if __name__ == __import__('base64').b64decode(b'X19tYWluX18=').decode():
    _f56cda8694e7()