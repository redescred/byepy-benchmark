"""CSV and table output formatters."""
import csv
import io
from typing import Any


class CSVFormatter:
    """Serialise row data back to CSV text."""

    def __init__(self, delimiter: str = ',', quoting: int = csv.QUOTE_MINIMAL) -> None:
        self.delimiter = delimiter
        self.quoting = quoting

    def format(self, headers: list[str], rows: list[list[Any]]) -> str:
        """Return CSV string from headers + row data."""
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=self.delimiter, quoting=self.quoting)
        if headers:
            writer.writerow(headers)
        for row in rows:
            writer.writerow([str(v) if v is not None else '' for v in row])
        return buf.getvalue()

    def format_dicts(self, records: list[dict[str, Any]]) -> str:
        """Format a list of dicts as CSV, inferring headers from first record."""
        if not records:
            return ''
        headers = list(records[0].keys())
        rows = [[r.get(h) for h in headers] for r in records]
        return self.format(headers, rows)


class TableFormatter:
    """Render rows as a human-readable fixed-width table."""

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
        """Format list of dicts as a table, inferring headers from first record."""
        if not records:
            return '(empty)'
        headers = list(records[0].keys())
        rows = [[r.get(h) for h in headers] for r in records]
        return self.format(headers, rows)


if __name__ == '__main__':
    from parser import CSVParser

    sample = (
        'name,age,city,active\n'
        'Alice,30,London,true\n'
        'Bob,25,Manchester,false\n'
        'Carol,35,London,true\n'
        'Dave,28,Edinburgh,true\n'
    )
    parser = CSVParser().parse(sample)
    records = parser.dicts()
    print('=== CSV output ===')
    print(CSVFormatter().format_dicts(records))
    print('=== Table output ===')
    tbl = TableFormatter()
    print(tbl.format_dicts(records))
    print('=== London residents sorted by age ===')
    london = parser.filter_rows(lambda r: r['city'] == 'London').sort_by('age')
    print(tbl.format_dicts(london.dicts()))
