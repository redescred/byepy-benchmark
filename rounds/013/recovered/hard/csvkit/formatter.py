"""CSV and table output formatters."""

import csv
import io
from typing import Any


class CSVFormatter:

    def __init__(self, delimiter=',', quoting=csv.QUOTE_MINIMAL):
        self.delimiter = delimiter
        self.quoting = quoting

    def format(self, headers, rows):
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=self.delimiter, quoting=self.quoting)
        if headers:
            writer.writerow(headers)
        for row in rows:
            writer.writerow([str(cell) if cell is not None else '' for cell in row])
        return buf.getvalue()

    def format_dicts(self, records):
        if not records:
            return ''
        headers = list(records[0].keys())
        rows = [[record.get(col) for col in headers] for record in records]
        return self.format(headers, rows)


class TableFormatter:

    def __init__(self, padding=1, border=True):
        self.padding = padding
        self.border = border

    def _col_widths(self, headers, rows):
        widths = [len(str(h)) for h in headers]
        for row in rows:
            for col_idx, cell in enumerate(row):
                if col_idx < len(widths):
                    widths[col_idx] = max(widths[col_idx], len(str(cell) if cell is not None else ''))
        return widths

    def _pad(self, value, width):
        text = str(value) if value is not None else ''
        return text.ljust(width)

    def format(self, headers, rows):
        widths = self._col_widths(headers, rows)
        pad = ' ' * self.padding
        separator = '+' + '+'.join(('-' * (w + self.padding * 2) for w in widths)) + '+'
        lines = []
        if self.border:
            lines.append(separator)
        header_row = '|' + '|'.join(
            (pad + self._pad(h, widths[i]) + pad for i, h in enumerate(headers))
        ) + '|'
        lines.append(header_row)
        if self.border:
            lines.append(separator)
        for row in rows:
            cells = []
            for col_idx, width in enumerate(widths):
                cell = row[col_idx] if col_idx < len(row) else ''
                cells.append(pad + self._pad(cell, width) + pad)
            lines.append('|' + '|'.join(cells) + '|')
        if self.border:
            lines.append(separator)
        return '\n'.join(lines)

    def format_dicts(self, records):
        if not records:
            return '(empty)'
        headers = list(records[0].keys())
        rows = [[record.get(col) for col in headers] for record in records]
        return self.format(headers, rows)
