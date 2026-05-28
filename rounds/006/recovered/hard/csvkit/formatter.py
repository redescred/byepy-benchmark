"""CSV and table output formatters."""
import csv
import io
from typing import Any


class CSVFormatter:
    def __init__(self, delimiter: str = ',', quoting: int = csv.QUOTE_MINIMAL):
        self.delimiter = delimiter
        self.quoting = quoting

    def format(self, headers: list[str], rows: list[list[Any]]) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=self.delimiter, quoting=self.quoting)
        if headers:
            writer.writerow(headers)
        for row in rows:
            writer.writerow([str(cell) if cell is not None else '' for cell in row])
        return buffer.getvalue()

    def format_dicts(self, records: list[dict[str, Any]]) -> str:
        if not records:
            return ''
        headers = list(records[0].keys())
        rows = [[record.get(h) for h in headers] for record in records]
        return self.format(headers, rows)


class TableFormatter:
    def __init__(self, padding: int = 1, border: bool = True):
        self.padding = padding
        self.border = border

    def _col_widths(self, headers: list[str], rows: list[list[Any]]) -> list[int]:
        widths = [len(str(h)) for h in headers]
        for row in rows:
            for i, value in enumerate(row):
                if i < len(widths):
                    widths[i] = max(widths[i], len(str(value) if value is not None else ''))
        return widths

    def _pad(self, value: Any, width: int) -> str:
        text = str(value) if value is not None else ''
        return text.ljust(width)

    def format(self, headers: list[str], rows: list[list[Any]]) -> str:
        widths = self._col_widths(headers, rows)
        pad = ' ' * self.padding
        separator = '+' + '+'.join('-' * (w + 2 * self.padding) for w in widths) + '+'
        lines = []
        if self.border:
            lines.append(separator)
        header_line = '|' + '|'.join(pad + self._pad(h, widths[i]) + pad for i, h in enumerate(headers)) + '|'
        lines.append(header_line)
        if self.border:
            lines.append(separator)
        for row in rows:
            cells = []
            for i, header in enumerate(headers):
                value = row[i] if i < len(row) else ''
                cells.append(pad + self._pad(value, widths[i]) + pad)
            lines.append('|' + '|'.join(cells) + '|')
        if self.border:
            lines.append(separator)
        return '\n'.join(lines)

    def format_dicts(self, records: list[dict[str, Any]]) -> str:
        if not records:
            return '(empty)'
        headers = list(records[0].keys())
        rows = [[record.get(h) for h in headers] for record in records]
        return self.format(headers, rows)
