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
        rows = [[rec.get(h) for h in headers] for rec in records]
        return self.format(headers, rows)


class TableFormatter:
    def __init__(self, padding: int = 1, border: bool = True) -> None:
        self.padding = padding
        self.border = border

    def _col_widths(self, headers: list[str], rows: list[list[Any]]) -> list[int]:
        widths = [len(str(h)) for h in headers]
        for row in rows:
            for i, val in enumerate(row):
                if i < len(widths):
                    widths[i] = max(widths[i], len(str(val) if val is not None else ''))
        return widths

    def _pad(self, value: Any, width: int) -> str:
        s = str(value) if value is not None else ''
        return s.ljust(width)

    def format(self, headers: list[str], rows: list[list[Any]]) -> str:
        col_widths = self._col_widths(headers, rows)
        pad = ' ' * self.padding
        border_line = '+' + '+'.join(
            '-' * (w + 2 * self.padding) for w in col_widths
        ) + '+'
        lines = []
        if self.border:
            lines.append(border_line)
        header_row = '|' + '|'.join(
            pad + self._pad(h, col_widths[i]) + pad
            for i, h in enumerate(headers)
        ) + '|'
        lines.append(header_row)
        if self.border:
            lines.append(border_line)
        for row in rows:
            cells = []
            for i, w in enumerate(col_widths):
                val = row[i] if i < len(row) else ''
                cells.append(pad + self._pad(val, w) + pad)
            lines.append('|' + '|'.join(cells) + '|')
        if self.border:
            lines.append(border_line)
        return '\n'.join(lines)

    def format_dicts(self, records: list[dict[str, Any]]) -> str:
        if not records:
            return ''
        headers = list(records[0].keys())
        rows = [[rec.get(h) for h in headers] for rec in records]
        return self.format(headers, rows)
