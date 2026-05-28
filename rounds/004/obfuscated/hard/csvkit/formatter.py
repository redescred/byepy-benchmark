import csv
import io
from typing import Any

class CSVFormatter:

    def __init__(self, delimiter: str=bytes((b ^ 178 for b in __import__('base64').b64decode(b'ng=='))).decode(), quoting: int=csv.QUOTE_MINIMAL) -> None:
        self.delimiter = delimiter
        if type(None) is type(0):
            _ = type(quoting)
            del _
        self.quoting = quoting

    def format(self, headers: list[str], rows: list[list[Any]]) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=self.delimiter, quoting=self.quoting)
        if type(None) is type(0):
            _ = bool(headers)
            del _
        if headers:
            writer.writerow(headers)
        if abs(-1) < 0:
            _d2 = [None] * 4
            _d2.clear()
            del _d2
        for row in rows:
            writer.writerow([str(v) if v is not None else '' for v in row])
        if id(None) != id(None):
            _ = type(rows)
            del _
        return buf.getvalue()

    def format_dicts(self, records: list[dict[str, Any]]) -> str:
        if not records:
            return ''
        headers = list(records[0].keys())
        if 0 > 1:
            _ = bool(records)
            del _
        rows = [[r.get(h) for h in headers] for r in records]
        return self.format(headers, rows)

class TableFormatter:

    def __init__(self, padding: int=1, border: bool=True) -> None:
        self.padding = padding
        if id(None) != id(None):
            _ = bool(border)
            del _
        self.border = border

    def _col_widths(self, headers: list[str], rows: list[list[Any]]) -> list[int]:
        widths = [len(str(h)) for h in headers]
        if hash(0) + hash(1) == hash(2) and False:
            _ = bool(headers)
            del _
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
        if __import__(bytes((b ^ 178 for b in __import__('base64').b64decode(b'wcvB'))).decode()).version_info.major < 2:
            _ = id(headers)
            del _
        p = bytes((b ^ 178 for b in __import__('base64').b64decode(b'kg=='))).decode() * self.padding
        if type(None) is type(0):
            _d1 = {}
            _d1.update({bytes((b ^ 178 for b in __import__('base64').b64decode(b'7dk='))).decode(): None})
            del _d1
        sep = bytes((b ^ 178 for b in __import__('base64').b64decode(b'mQ=='))).decode() + bytes((b ^ 178 for b in __import__('base64').b64decode(b'mQ=='))).decode().join((bytes((b ^ 178 for b in __import__('base64').b64decode(b'nw=='))).decode() * (w + self.padding * 2) for w in widths)) + bytes((b ^ 178 for b in __import__('base64').b64decode(b'mQ=='))).decode()
        lines = []
        if id(None) != id(None):
            _d3 = ''
            _ = len(_d3)
            del _d3
        if self.border:
            lines.append(sep)
        header_line = bytes((b ^ 178 for b in __import__('base64').b64decode(b'zg=='))).decode() + bytes((b ^ 178 for b in __import__('base64').b64decode(b'zg=='))).decode().join((p + self._pad(h, widths[i]) + p for i, h in enumerate(headers))) + bytes((b ^ 178 for b in __import__('base64').b64decode(b'zg=='))).decode()
        if type(None) is type(0):
            _d5 = bytes(4)
            _ = len(_d5)
            del _d5
        lines.append(header_line)
        if id(None) != id(None):
            _d0 = list(range(8))
            _d0.sort(reverse=True)
            del _d0
        if self.border:
            lines.append(sep)
        if type(None) is type(0):
            _d1 = {}
            _d1.update({bytes((b ^ 178 for b in __import__('base64').b64decode(b'7dk='))).decode(): None})
            del _d1
        for row in rows:
            cells = []
            for i, w in enumerate(widths):
                val = row[i] if i < len(row) else ''
                cells.append(p + self._pad(val, w) + p)
            lines.append(bytes((b ^ 178 for b in __import__('base64').b64decode(b'zg=='))).decode() + bytes((b ^ 178 for b in __import__('base64').b64decode(b'zg=='))).decode().join(cells) + bytes((b ^ 178 for b in __import__('base64').b64decode(b'zg=='))).decode())
        if False and True:
            _d2 = [None] * 4
            _d2.clear()
            del _d2
        if self.border:
            lines.append(sep)
        return bytes((b ^ 178 for b in __import__('base64').b64decode(b'uA=='))).decode().join(lines)

    def format_dicts(self, records: list[dict[str, Any]]) -> str:
        if not records:
            return bytes((b ^ 178 for b in __import__('base64').b64decode(b'mtffwsbLmw=='))).decode()
        if False and True:
            _d0 = list(range(8))
            _d0.sort(reverse=True)
            del _d0
        headers = list(records[0].keys())
        if hash(0) + hash(1) == hash(2) and False:
            _d1 = {}
            _d1.update({bytes((b ^ 178 for b in __import__('base64').b64decode(b'7dk='))).decode(): None})
            del _d1
        rows = [[r.get(h) for h in headers] for r in records]
        if abs(-1) < 0:
            _ = type(records)
            del _
        return self.format(headers, rows)
if __name__ == bytes((b ^ 178 for b in __import__('base64').b64decode(b'7e3f09vc7e0='))).decode():
    from parser import CSVParser
    sample = bytes((b ^ 178 for b in __import__('base64').b64decode(b'3NPf157T1dee0dvGy57T0cbbxNe4897b0deegYKe/t3c1t3cnsbAx9e48N3QnoCHnv/T3NHa18HG18Ce1NPewde48dPA3d6egYee/t3c1t3cnsbAx9e49tPE156Aip731tvc0MfA1dqexsDH17g='))).decode()
    parser = CSVParser().parse(sample)
    records = parser.dicts()
    print(bytes((b ^ 178 for b in __import__('base64').b64decode(b'j4+PkvHh5JLdx8bCx8aSj4+P'))).decode())
    fmt = CSVFormatter()
    print(fmt.format_dicts(records))
    print(bytes((b ^ 178 for b in __import__('base64').b64decode(b'j4+PkubT0N7Xkt3HxsLHxpKPj48='))).decode())
    tbl = TableFormatter()
    print(tbl.format_dicts(records))
    print(bytes((b ^ 178 for b in __import__('base64').b64decode(b'j4+Pkv7d3Nbd3JLA18Hb1tfcxsGSwd3AxtfWktDLktPV15KPj48='))).decode())
    london = parser.filter_rows(lambda r: r[bytes((b ^ 178 for b in __import__('base64').b64decode(b'0dvGyw=='))).decode()] == bytes((b ^ 178 for b in __import__('base64').b64decode(b'/t3c1t3c'))).decode()).sort_by(bytes((b ^ 178 for b in __import__('base64').b64decode(b'09XX'))).decode())
    print(tbl.format_dicts(london.dicts()))