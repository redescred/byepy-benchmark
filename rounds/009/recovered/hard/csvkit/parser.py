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
        stripped = value.strip()
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
            pass
        return stripped

    def parse(self, text):
        reader = csv.reader(io.StringIO(text), delimiter=self.delimiter)
        all_rows = list(reader)
        if not all_rows:
            return self
        start = 0
        if self.has_header:
            self.headers = [h.strip() for h in all_rows[0]]
            start = 1
        for raw_row in all_rows[start:None]:
            if self.skip_blank:
                if all((cell.strip() == '' for cell in raw_row)):
                    continue
            if self.infer_types:
                self._rows.append([self._coerce(cell) for cell in raw_row])
            else:
                self._rows.append([cell.strip() for cell in raw_row])
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
            col_idx = self.headers.index(name_or_index)
        else:
            col_idx = name_or_index
        return [row[col_idx] for row in self._rows]

    def filter_rows(self, predicate):
        result = CSVParser(delimiter=self.delimiter, has_header=self.has_header, infer_types=self.infer_types, skip_blank=self.skip_blank)
        result.headers = list(self.headers)
        result._rows = [row for row in self._rows if predicate(dict(zip(self.headers, row)))]
        return result

    def sort_by(self, column, reverse=False):
        if column not in self.headers:
            raise CSVError(f"Column '{column}' not found")
        col_idx = self.headers.index(column)
        result = CSVParser(delimiter=self.delimiter, has_header=self.has_header, infer_types=self.infer_types, skip_blank=self.skip_blank)
        result.headers = list(self.headers)
        result._rows = sorted(self._rows, key=lambda r: (r[col_idx] is None, r[col_idx]), reverse=reverse)
        return result

    def __len__(self):
        return len(self._rows)

    def __iter__(self):
        return iter(self.dicts())
