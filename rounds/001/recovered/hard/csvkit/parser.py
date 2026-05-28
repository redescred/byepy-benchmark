"""CSV parser with type inference and error handling."""
import csv
import io
from typing import Any, Iterator


class CSVError(Exception):
    """Raised for malformed or unreadable CSV input."""


class CSVParser:
    """Parse CSV text into typed rows with optional header handling."""

    BOOL_TRUE = {'true', 'yes', '1', 'on'}
    BOOL_FALSE = {'false', 'no', '0', 'off'}

    def __init__(self, delimiter: str = ',', has_header: bool = True,
                 infer_types: bool = True, skip_blank: bool = True) -> None:
        self.delimiter = delimiter
        self.has_header = has_header
        self.infer_types = infer_types
        self.skip_blank = skip_blank
        self.headers: list[str] = []
        self._rows: list[list[Any]] = []

    def _coerce(self, value: str) -> Any:
        """Attempt to convert a string to int, float, bool, or leave as str."""
        v = value.strip()
        if v == '':
            return None
        if v.lower() in self.BOOL_TRUE:
            return True
        if v.lower() in self.BOOL_FALSE:
            return False
        try:
            return int(v)
        except ValueError:
            pass
        try:
            return float(v)
        except ValueError:
            pass
        return v

    def parse(self, text: str) -> 'CSVParser':
        """Parse CSV text. Returns self for chaining."""
        reader = csv.reader(io.StringIO(text), delimiter=self.delimiter)
        rows = list(reader)
        if not rows:
            return self
        start = 0
        if self.has_header:
            self.headers = [h.strip() for h in rows[0]]
            start = 1
        for row in rows[start:]:
            if self.skip_blank and all(c.strip() == '' for c in row):
                continue
            if self.infer_types:
                self._rows.append([self._coerce(c) for c in row])
            else:
                self._rows.append([c.strip() for c in row])
        return self

    def rows(self) -> list[list[Any]]:
        """Return all parsed rows as lists."""
        return list(self._rows)

    def dicts(self) -> list[dict[str, Any]]:
        """Return rows as dicts keyed by header. Raises if no headers."""
        if not self.headers:
            raise CSVError('No headers available; parse with has_header=True')
        return [dict(zip(self.headers, row)) for row in self._rows]

    def column(self, name_or_index: str | int) -> list[Any]:
        """Extract a single column by header name or index."""
        if isinstance(name_or_index, str):
            if name_or_index not in self.headers:
                raise CSVError(f"Column '{name_or_index}' not found")
            idx = self.headers.index(name_or_index)
        else:
            idx = name_or_index
        return [row[idx] if idx < len(row) else None for row in self._rows]

    def filter_rows(self, predicate) -> 'CSVParser':
        """Return a new CSVParser containing only rows where predicate(dict) is True."""
        result = CSVParser(
            delimiter=self.delimiter,
            has_header=self.has_header,
            infer_types=self.infer_types,
            skip_blank=self.skip_blank,
        )
        result.headers = list(self.headers)
        result._rows = [row for row in self._rows if predicate(dict(zip(self.headers, row)))]
        return result

    def sort_by(self, column: str, reverse: bool = False) -> 'CSVParser':
        """Return a new CSVParser with rows sorted by a column."""
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

    def __len__(self) -> int:
        return len(self._rows)

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self.dicts())
