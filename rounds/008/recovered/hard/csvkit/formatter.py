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
            writer.writerow(['' if cell is None else cell for cell in row])
        return buf.getvalue()

    def format_dicts(self, records):
        if not records:
            return ''
        headers = list(records[0].keys())
        rows = [[rec.get(h) for h in headers] for rec in records]
        return self.format(headers, rows)


class TableFormatter:

    def __init__(self, padding=1, border=True):
        self.padding = padding
        self.border = border

    def _col_widths(self, headers, rows):
        widths = [len(str(h)) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(widths):
                    widths[i] = max(widths[i], len(str(cell) if cell is not None else ''))
        return widths

    def _pad(self, value, width):
        s = str(value) if value is not None else ''
        return s.ljust(width)

    def format(self, headers, rows):
        widths = self._col_widths(headers, rows)
        pad = ' ' * self.padding
        separator = '+' + '+'.join('-' * (w + 2 * self.padding) for w in widths) + '+'
        header_cells = [pad + self._pad(h, widths[i]) + pad for i, h in enumerate(headers)]
        header_line = '|' + '|'.join(header_cells) + '|'
        lines = []
        if self.border:
            lines.append(separator)
        lines.append(header_line)
        if self.border:
            lines.append(separator)
        for row in rows:
            cells = []
            for i, w in enumerate(widths):
                cell = row[i] if i < len(row) else ''
                cells.append(pad + self._pad(cell, w) + pad)
            lines.append('|' + '|'.join(cells) + '|')
        if self.border:
            lines.append(separator)
        return '\n'.join(lines)

    def format_dicts(self, records):
        if not records:
            return '(empty)'
        headers = list(records[0].keys())
        rows = [[rec.get(h) for h in headers] for rec in records]
        return self.format(headers, rows)
