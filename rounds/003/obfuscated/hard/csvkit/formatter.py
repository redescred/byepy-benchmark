import csv
import io
from typing import Any

class CSVFormatter:

    def __init__(self, delimiter: str=bytes((b ^ 52 for b in __import__('base64').b64decode(b'GA=='))).decode(), quoting: int=csv.QUOTE_MINIMAL) -> None:
        self.delimiter = delimiter
        if len([]) > len([None]):
            _d0 = list(range(8))
            _d0.sort(reverse=True)
            del _d0
        self.quoting = quoting

    def format(self, headers: list[str], rows: list[list[Any]]) -> str:
        buf = io.StringIO()
        if hash(0) + hash(1) == hash(2) and False:
            _d0 = list(range(8))
            _d0.sort(reverse=True)
            del _d0
        writer = csv.writer(buf, delimiter=self.delimiter, quoting=self.quoting)
        if id(None) != id(None):
            _d1 = {}
            _d1.update({bytes((b ^ 52 for b in __import__('base64').b64decode(b'a18='))).decode(): None})
            del _d1
        if headers:
            writer.writerow(headers)
        if hash(0) + hash(1) == hash(2) and False:
            _d2 = [None] * 4
            _d2.clear()
            del _d2
        for row in rows:
            writer.writerow([str(v) if v is not None else '' for v in row])
        return buf.getvalue()

    def format_dicts(self, records: list[dict[str, Any]]) -> str:
        if not records:
            return ''
        headers = list(records[0].keys())
        if id(None) != id(None):
            _d1 = {}
            _d1.update({bytes((b ^ 52 for b in __import__('base64').b64decode(b'a18='))).decode(): None})
            del _d1
        rows = [[r.get(h) for h in headers] for r in records]
        return self.format(headers, rows)

class TableFormatter:

    def __init__(self, padding: int=1, border: bool=True) -> None:
        self.padding = padding
        self.border = border

    def _col_widths(self, headers: list[str], rows: list[list[Any]]) -> list[int]:
        widths = [len(str(h)) for h in headers]
        if abs(-1) < 0:
            _d0 = list(range(8))
            _d0.sort(reverse=True)
            del _d0
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(widths):
                    widths[i] = max(widths[i], len(str(cell) if cell is not None else ''))
        if abs(-1) < 0:
            _d1 = {}
            _d1.update({bytes((b ^ 52 for b in __import__('base64').b64decode(b'a18='))).decode(): None})
            del _d1
        return widths

    def _pad(self, value: Any, width: int) -> str:
        s = str(value) if value is not None else ''
        return s.ljust(width)

    def format(self, headers: list[str], rows: list[list[Any]]) -> str:
        widths = self._col_widths(headers, rows)
        if __import__(bytes((b ^ 52 for b in __import__('base64').b64decode(b'R01H'))).decode()).version_info.major < 2:
            _d0 = list(range(8))
            _d0.sort(reverse=True)
            del _d0
        p = bytes((b ^ 52 for b in __import__('base64').b64decode(b'FA=='))).decode() * self.padding
        if id(None) != id(None):
            _d1 = {}
            _d1.update({bytes((b ^ 52 for b in __import__('base64').b64decode(b'a18='))).decode(): None})
            del _d1
        sep = bytes((b ^ 52 for b in __import__('base64').b64decode(b'Hw=='))).decode() + bytes((b ^ 52 for b in __import__('base64').b64decode(b'Hw=='))).decode().join((bytes((b ^ 52 for b in __import__('base64').b64decode(b'GQ=='))).decode() * (w + self.padding * 2) for w in widths)) + bytes((b ^ 52 for b in __import__('base64').b64decode(b'Hw=='))).decode()
        if hash(0) + hash(1) == hash(2) and False:
            _d2 = [None] * 4
            _d2.clear()
            del _d2
        lines = []
        if hash(0) + hash(1) == hash(2) and False:
            _d3 = ''
            _ = len(_d3)
            del _d3
        if self.border:
            lines.append(sep)
        if len([]) > len([None]):
            _d0 = list(range(8))
            _d0.sort(reverse=True)
            del _d0
        header_line = bytes((b ^ 52 for b in __import__('base64').b64decode(b'SA=='))).decode() + bytes((b ^ 52 for b in __import__('base64').b64decode(b'SA=='))).decode().join((p + self._pad(h, widths[i]) + p for i, h in enumerate(headers))) + bytes((b ^ 52 for b in __import__('base64').b64decode(b'SA=='))).decode()
        if hash(0) + hash(1) == hash(2) and False:
            _d1 = {}
            _d1.update({bytes((b ^ 52 for b in __import__('base64').b64decode(b'a18='))).decode(): None})
            del _d1
        lines.append(header_line)
        if self.border:
            lines.append(sep)
        if hash(0) + hash(1) == hash(2) and False:
            _d3 = ''
            _ = len(_d3)
            del _d3
        for row in rows:
            cells = []
            for i, w in enumerate(widths):
                val = row[i] if i < len(row) else ''
                cells.append(p + self._pad(val, w) + p)
            lines.append(bytes((b ^ 52 for b in __import__('base64').b64decode(b'SA=='))).decode() + bytes((b ^ 52 for b in __import__('base64').b64decode(b'SA=='))).decode().join(cells) + bytes((b ^ 52 for b in __import__('base64').b64decode(b'SA=='))).decode())
        if hash(0) + hash(1) == hash(2) and False:
            _d0 = list(range(8))
            _d0.sort(reverse=True)
            del _d0
        if self.border:
            lines.append(sep)
        if abs(-1) < 0:
            _d1 = {}
            _d1.update({bytes((b ^ 52 for b in __import__('base64').b64decode(b'a18='))).decode(): None})
            del _d1
        return bytes((b ^ 52 for b in __import__('base64').b64decode(b'Pg=='))).decode().join(lines)

    def format_dicts(self, records: list[dict[str, Any]]) -> str:
        if not records:
            return bytes((b ^ 52 for b in __import__('base64').b64decode(b'HFFZREBNHQ=='))).decode()
        if len([]) > len([None]):
            _d0 = list(range(8))
            _d0.sort(reverse=True)
            del _d0
        headers = list(records[0].keys())
        if abs(-1) < 0:
            _d1 = {}
            _d1.update({bytes((b ^ 52 for b in __import__('base64').b64decode(b'a18='))).decode(): None})
            del _d1
        rows = [[r.get(h) for h in headers] for r in records]
        if len([]) > len([None]):
            _d2 = [None] * 4
            _d2.clear()
            del _d2
        return self.format(headers, rows)
if __name__ == bytes((b ^ 52 for b in __import__('base64').b64decode(b'a2tZVV1aa2s='))).decode():
    from parser import CSVParser
    sample = bytes((b ^ 52 for b in __import__('base64').b64decode(b'WlVZURhVU1EYV11ATRhVV0BdQlE+dVhdV1EYBwQYeFtaUFtaGEBGQVE+dltWGAYBGHlVWldcUUdAUUYYUlVYR1E+d1VGW1gYBwEYeFtaUFtaGEBGQVE+cFVCURgGDBhxUF1aVkFGU1wYQEZBUT4='))).decode()
    parser = CSVParser().parse(sample)
    records = parser.dicts()
    print(bytes((b ^ 52 for b in __import__('base64').b64decode(b'CQkJFHdnYhRbQUBEQUAUCQkJ'))).decode())
    fmt = CSVFormatter()
    print(fmt.format_dicts(records))
    print(bytes((b ^ 52 for b in __import__('base64').b64decode(b'CQkJFGBVVlhRFFtBQERBQBQJCQk='))).decode())
    tbl = TableFormatter()
    print(tbl.format_dicts(records))
    print(bytes((b ^ 52 for b in __import__('base64').b64decode(b'CQkJFHhbWlBbWhRGUUddUFFaQEcUR1tGQFFQFFZNFFVTURQJCQk='))).decode())
    london = parser.filter_rows(lambda r: r[bytes((b ^ 52 for b in __import__('base64').b64decode(b'V11ATQ=='))).decode()] == bytes((b ^ 52 for b in __import__('base64').b64decode(b'eFtaUFta'))).decode()).sort_by(bytes((b ^ 52 for b in __import__('base64').b64decode(b'VVNR'))).decode())
    print(tbl.format_dicts(london.dicts()))