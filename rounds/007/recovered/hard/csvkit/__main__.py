__all__ = ['CSVParser', 'CSVError', 'CSVFormatter', 'TableFormatter']
__version__ = '0.1.0'

'CSV and table output formatters.'

import csv
import io
from typing import Any


class CSVFormatter:
    def __init__(self, delimiter=',', quoting=csv.QUOTE_MINIMAL):
        self.delimiter = delimiter
        self.quoting = quoting

    def format(self, headers, rows):
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=self.delimiter, quoting=self.quoting)
        if headers:
            writer.writerow(headers)
        for row in rows:
            writer.writerow([str(v) if v is not None else '' for v in row])
        return buffer.getvalue()

    def format_dicts(self, records):
        if not records:
            return ''
        headers = list(records[0].keys())
        rows = [[record.get(h) for h in headers] for record in records]
        return self.format(headers, rows)


class TableFormatter:
    def __init__(self, padding=1, border=True):
        self.padding = padding
        self.border = border

    def _col_widths(self, headers, rows):
        widths = [len(str(h)) for h in headers]
        for row in rows:
            for index, value in enumerate(row):
                if index < len(widths):
                    widths[index] = max(widths[index], len(str(value) if value is not None else ''))
        return widths

    def _pad(self, value, width):
        text = str(value) if value is not None else ''
        return text.ljust(width)

    def format(self, headers, rows):
        widths = self._col_widths(headers, rows)
        pad = ' ' * self.padding
        separator = '+' + '+'.join('-' * (w + self.padding * 2) for w in widths) + '+'
        lines = []
        if self.border:
            lines.append(separator)
        header_line = '|' + '|'.join(pad + self._pad(h, w) + pad for h, w in zip(headers, widths)) + '|'
        lines.append(header_line)
        if self.border:
            lines.append(separator)
        for row in rows:
            cells = []
            for index, width in enumerate(widths):
                value = row[index] if index < len(row) else ''
                cells.append(pad + self._pad(value, width) + pad)
            lines.append('|' + '|'.join(cells) + '|')
        if self.border:
            lines.append(separator)
        return '\n'.join(lines)

    def format_dicts(self, records):
        if not records:
            return '(empty)'
        headers = list(records[0].keys())
        rows = [[record.get(h) for h in headers] for record in records]
        return self.format(headers, rows)


'CSV parser with type inference and error handling.'

import csv
import io
from typing import Any, Iterator


class CSVError(Exception):
    pass


class CSVParser:
    BOOL_TRUE = {'true', 'yes', '1', 'on'}
    BOOL_FALSE = {'false', 'no', '0', 'off'}

    def __init__(self, delimiter=',', has_header=True, infer_types=True, skip_blank=True):
        self.delimiter = delimiter
        self.has_header = has_header
        self.infer_types = infer_types
        self.skip_blank = skip_blank
        self.headers = None
        self._rows = []

    def _coerce(self, value):
        stripped = value.strip()
        if stripped == '':
            return None
        if stripped.lower() in self.BOOL_TRUE:
            return True
        if stripped.lower() in self.BOOL_FALSE:
            return False
        try:
            return int(stripped)
        except ValueError:
            pass
        try:
            return float(stripped)
        except ValueError:
            return stripped

    def parse(self, text):
        reader = csv.reader(io.StringIO(text), delimiter=self.delimiter)
        rows = list(reader)
        if not rows:
            return self
        start = 0
        if self.has_header:
            self.headers = [h.strip() for h in rows[0]]
            start = 1
        for row in rows[start:]:
            if self.skip_blank and all(cell.strip() == '' for cell in row):
                continue
            if self.infer_types:
                self._rows.append([self._coerce(cell) for cell in row])
            else:
                self._rows.append([cell.strip() for cell in row])
        return self

    def rows(self):
        return list(self._rows)

    def dicts(self):
        if not self.headers:
            raise CSVError('No headers available; parse with has_header=True')
        return [dict(zip(self.headers, row)) for row in self._rows]

    def column(self, name_or_index):
        if isinstance(name_or_index, str):
            if name_or_index not in self.headers:
                raise CSVError(f"Column '{name_or_index}' not found")
            index = self.headers.index(name_or_index)
        else:
            index = name_or_index
        return [row[index] if index < len(row) else None for row in self._rows]

    def filter_rows(self, predicate):
        result = CSVParser(
            delimiter=self.delimiter,
            has_header=self.has_header,
            infer_types=self.infer_types,
            skip_blank=self.skip_blank,
        )
        result.headers = list(self.headers)
        result._rows = [row for row in self._rows if predicate(dict(zip(self.headers, row)))]
        return result

    def sort_by(self, column, reverse=False):
        if column not in self.headers:
            raise CSVError(f"Column '{column}' not found")
        index = self.headers.index(column)
        result = CSVParser(
            delimiter=self.delimiter,
            has_header=self.has_header,
            infer_types=self.infer_types,
            skip_blank=self.skip_blank,
        )
        result.headers = list(self.headers)
        result._rows = sorted(self._rows, key=lambda r: (r[index] is None, r[index]), reverse=reverse)
        return result

    def __len__(self):
        return len(self._rows)

    def __iter__(self):
        return iter(self.dicts())


'Entry point: python -m csvkit'

SAMPLE = (
    'name,age,city,active\n'
    'Alice,30,London,true\n'
    'Bob,25,Manchester,false\n'
    'Carol,35,London,true\n'
    'Dave,28,Edinburgh,true\n'
)


def demo():
    parser = CSVParser().parse(SAMPLE)
    records = parser.dicts()
    print('=== CSV round-trip ===')
    print(CSVFormatter().format_dicts(records))
    print('=== Table ===')
    print(TableFormatter().format_dicts(records))
    print('=== London, sorted by age ===')
    london = parser.filter_rows(lambda r: r['city'] == 'London').sort_by('age')
    print(TableFormatter().format_dicts(london.dicts()))
    print(f'Total rows: {len(parser)}')


if __name__ == '__main__':
    demo()
