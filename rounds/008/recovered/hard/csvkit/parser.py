"""CSV parser with type inference and error handling."""
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
        self.headers = []
        self._rows = []

    def _coerce(self, value):
        s = value.strip()
        if s.lower() in self.BOOL_TRUE:
            return True
        if s.lower() in self.BOOL_FALSE:
            return False
        try:
            return int(s)
        except ValueError:
            pass
        try:
            return float(s)
        except ValueError:
            return s

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
            idx = self.headers.index(name_or_index)
        else:
            idx = name_or_index
        return [row[idx] if idx < len(row) else None for row in self._rows]

    def filter_rows(self, predicate):
        result = CSVParser(
            delimiter=self.delimiter,
            has_header=self.has_header,
            infer_types=self.infer_types,
            skip_blank=self.skip_blank,
        )
        result.headers = list(self.headers)
        result._rows = [row for row in self._rows
                        if predicate(dict(zip(self.headers, row)))]
        return result

    def sort_by(self, column, reverse=False):
        if column not in self.headers:
            raise CSVError(f"Column '{column}' not found")
        idx = self.headers.index(column)
        result = CSVParser(
            delimiter=self.delimiter,
            has_header=self.has_header,
            infer_types=self.infer_types,
            skip_blank=self.skip_blank,
        )
        result.headers = list(self.headers)
        result._rows = sorted(
            self._rows,
            key=lambda r: (r[idx] is None, r[idx]),
            reverse=reverse,
        )
        return result

    def __len__(self):
        return len(self._rows)

    def __iter__(self):
        return iter(self.dicts())
