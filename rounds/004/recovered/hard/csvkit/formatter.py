import csv
import io
from typing import Any


class CSVFormatter:

    def __init__(self, delimiter: str = ',', quoting: int = csv.QUOTE_MINIMAL) -> None:
        self.delimiter = delimiter
        self.quoting = quoting

    def format(self, headers: list[str], rows: list[list[Any]]) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=self.delimiter, quoting=self.quoting)
        if headers:
            writer.writerow(headers)
        for row in rows:
            writer.writerow([str(v) if v is not None else '' for v in row])
        return buf.getvalue()

    def format_dicts(self, records: list[dict[str, Any]]) -> str:
        if not records:
            return ''
        headers = list(records[0].keys())
        rows = [[r.get(h) for h in headers] for r in records]
        return self.format(headers, rows)


class TableFormatter:

    def __init__(self, padding: int = 1, border: bool = True) -> None:
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
        p = ' ' * self.padding
        sep = '+' + '+'.join('-' * (w + self.padding * 2) for w in widths) + '+'
        lines = []
        if self.border:
            lines.append(sep)
        header_line = '|' + '|'.join(p + self._pad(h, widths[i]) + p for i, h in enumerate(headers)) + '|'
        lines.append(header_line)
        if self.border:
            lines.append(sep)
        for row in rows:
            cells = []
            for i, w in enumerate(widths):
                val = row[i] if i < len(row) else ''
                cells.append(p + self._pad(val, w) + p)
            lines.append('|' + '|'.join(cells) + '|')
        if self.border:
            lines.append(sep)
        return '\n'.join(lines)

    def format_dicts(self, records: list[dict[str, Any]]) -> str:
        if not records:
            return '(empty)'
        headers = list(records[0].keys())
        rows = [[r.get(h) for h in headers] for r in records]
        return self.format(headers, rows)
