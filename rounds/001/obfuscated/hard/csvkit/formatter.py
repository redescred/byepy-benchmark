__import__('base64').b64decode(b'Q1NWIGFuZCB0YWJsZSBvdXRwdXQgZm9ybWF0dGVycy4=').decode()
import csv
import io
from typing import Any

class CSVFormatter:
    __import__('base64').b64decode(b'U2VyaWFsaXNlIHJvdyBkYXRhIGJhY2sgdG8gQ1NWIHRleHQu').decode()

    def __init__(self, delimiter: str=__import__('base64').b64decode(b'LA==').decode(), quoting: int=csv.QUOTE_MINIMAL) -> None:
        self.delimiter = delimiter
        self.quoting = quoting

    def format(self, headers: list[str], rows: list[list[Any]]) -> str:
        __import__('base64').b64decode(b'UmV0dXJuIENTViBzdHJpbmcgZnJvbSBoZWFkZXJzICsgcm93IGRhdGEu').decode()
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=self.delimiter, quoting=self.quoting)
        if headers:
            writer.writerow(headers)
        for row in rows:
            writer.writerow([str(v) if v is not None else '' for v in row])
        return buf.getvalue()

    def format_dicts(self, records: list[dict[str, Any]]) -> str:
        __import__('base64').b64decode(b'Rm9ybWF0IGEgbGlzdCBvZiBkaWN0cyBhcyBDU1YsIGluZmVycmluZyBoZWFkZXJzIGZyb20gZmlyc3QgcmVjb3JkLg==').decode()
        if not records:
            return ''
        headers = list(records[0].keys())
        rows = [[r.get(h) for h in headers] for r in records]
        return self.format(headers, rows)

class TableFormatter:
    __import__('base64').b64decode(b'UmVuZGVyIHJvd3MgYXMgYSBodW1hbi1yZWFkYWJsZSBmaXhlZC13aWR0aCB0YWJsZS4=').decode()

    def __init__(self, padding: int=1, border: bool=True) -> None:
        self.padding = padding
        self.border = border

    def _col_widths(self, headers: list[str], rows: list[list[Any]]) -> list[int]:
        widths = [len(str(h)) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(widths):
                    widths[i] = max(widths[i], len(str(cell) if cell is not None else ''))
        return widths

    def _pad(self, value: Any, width: int) -> str:
        s = str(value) if value is not None else ''
        return s.ljust(width)

    def format(self, headers: list[str], rows: list[list[Any]]) -> str:
        widths = self._col_widths(headers, rows)
        p = __import__('base64').b64decode(b'IA==').decode() * self.padding
        sep = __import__('base64').b64decode(b'Kw==').decode() + __import__('base64').b64decode(b'Kw==').decode().join((__import__('base64').b64decode(b'LQ==').decode() * (w + self.padding * 2) for w in widths)) + __import__('base64').b64decode(b'Kw==').decode()
        lines = []
        if self.border:
            lines.append(sep)
        header_line = __import__('base64').b64decode(b'fA==').decode() + __import__('base64').b64decode(b'fA==').decode().join((p + self._pad(h, widths[i]) + p for i, h in enumerate(headers))) + __import__('base64').b64decode(b'fA==').decode()
        lines.append(header_line)
        if self.border:
            lines.append(sep)
        for row in rows:
            cells = []
            for i, w in enumerate(widths):
                val = row[i] if i < len(row) else ''
                cells.append(p + self._pad(val, w) + p)
            lines.append(__import__('base64').b64decode(b'fA==').decode() + __import__('base64').b64decode(b'fA==').decode().join(cells) + __import__('base64').b64decode(b'fA==').decode())
        if self.border:
            lines.append(sep)
        return __import__('base64').b64decode(b'Cg==').decode().join(lines)

    def format_dicts(self, records: list[dict[str, Any]]) -> str:
        __import__('base64').b64decode(b'Rm9ybWF0IGxpc3Qgb2YgZGljdHMgYXMgYSB0YWJsZSwgaW5mZXJyaW5nIGhlYWRlcnMgZnJvbSBmaXJzdCByZWNvcmQu').decode()
        if not records:
            return __import__('base64').b64decode(b'KGVtcHR5KQ==').decode()
        headers = list(records[0].keys())
        rows = [[r.get(h) for h in headers] for r in records]
        return self.format(headers, rows)
if __name__ == __import__('base64').b64decode(b'X19tYWluX18=').decode():
    from parser import CSVParser
    sample = __import__('base64').b64decode(b'bmFtZSxhZ2UsY2l0eSxhY3RpdmUKQWxpY2UsMzAsTG9uZG9uLHRydWUKQm9iLDI1LE1hbmNoZXN0ZXIsZmFsc2UKQ2Fyb2wsMzUsTG9uZG9uLHRydWUKRGF2ZSwyOCxFZGluYnVyZ2gsdHJ1ZQo=').decode()
    parser = CSVParser().parse(sample)
    records = parser.dicts()
    print(__import__('base64').b64decode(b'PT09IENTViBvdXRwdXQgPT09').decode())
    fmt = CSVFormatter()
    print(fmt.format_dicts(records))
    print(__import__('base64').b64decode(b'PT09IFRhYmxlIG91dHB1dCA9PT0=').decode())
    tbl = TableFormatter()
    print(tbl.format_dicts(records))
    print(__import__('base64').b64decode(b'PT09IExvbmRvbiByZXNpZGVudHMgc29ydGVkIGJ5IGFnZSA9PT0=').decode())
    london = parser.filter_rows(lambda r: r[__import__('base64').b64decode(b'Y2l0eQ==').decode()] == __import__('base64').b64decode(b'TG9uZG9u').decode()).sort_by(__import__('base64').b64decode(b'YWdl').decode())
    print(tbl.format_dicts(london.dicts()))