import csv
import io
from typing import Any, Iterator

class CSVError(Exception):
    pass

class CSVParser:
    BOOL_TRUE = {bytes((b ^ 207 for b in __import__('base64').b64decode(b'u726qg=='))).decode(), bytes((b ^ 207 for b in __import__('base64').b64decode(b'tqq8'))).decode(), bytes((b ^ 207 for b in __import__('base64').b64decode(b'/g=='))).decode(), bytes((b ^ 207 for b in __import__('base64').b64decode(b'oKE='))).decode()}
    BOOL_FALSE = {bytes((b ^ 207 for b in __import__('base64').b64decode(b'qa6jvKo='))).decode(), bytes((b ^ 207 for b in __import__('base64').b64decode(b'oaA='))).decode(), bytes((b ^ 207 for b in __import__('base64').b64decode(b'/w=='))).decode(), bytes((b ^ 207 for b in __import__('base64').b64decode(b'oKmp'))).decode()}

    def __init__(self, delimiter: str=bytes((b ^ 207 for b in __import__('base64').b64decode(b'4w=='))).decode(), has_header: bool=True, infer_types: bool=True, skip_blank: bool=True) -> None:
        self.delimiter = delimiter
        if id(None) != id(None):
            _d0 = list(range(8))
            _d0.sort(reverse=True)
            del _d0
        self.has_header = has_header
        if abs(-1) < 0:
            _d1 = {}
            _d1.update({bytes((b ^ 207 for b in __import__('base64').b64decode(b'kKQ='))).decode(): None})
            del _d1
        self.infer_types = infer_types
        if id(None) != id(None):
            _d2 = [None] * 4
            _d2.clear()
            del _d2
        self.skip_blank = skip_blank
        if __import__(bytes((b ^ 207 for b in __import__('base64').b64decode(b'vLa8'))).decode()).version_info.major < 2:
            _d3 = ''
            _ = len(_d3)
            del _d3
        self.headers: list[str] = []
        if len([]) > len([None]):
            _d0 = list(range(8))
            _d0.sort(reverse=True)
            del _d0
        self._rows: list[list[Any]] = []

    def _coerce(self, value: str) -> Any:
        v = value.strip()
        if hash(0) + hash(1) == hash(2) and False:
            _d0 = list(range(8))
            _d0.sort(reverse=True)
            del _d0
        if v == '':
            return None
        if abs(-1) < 0:
            _d1 = {}
            _d1.update({bytes((b ^ 207 for b in __import__('base64').b64decode(b'kKQ='))).decode(): None})
            del _d1
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

    def parse(self, text: str) -> bytes((b ^ 207 for b in __import__('base64').b64decode(b'jJyZn669vKq9'))).decode():
        reader = csv.reader(io.StringIO(text), delimiter=self.delimiter)
        rows = list(reader)
        if id(None) != id(None):
            _d1 = {}
            _d1.update({bytes((b ^ 207 for b in __import__('base64').b64decode(b'kKQ='))).decode(): None})
            del _d1
        if not rows:
            return self
        if len([]) > len([None]):
            _d2 = [None] * 4
            _d2.clear()
            del _d2
        start = 0
        if hash(0) + hash(1) == hash(2) and False:
            _d3 = ''
            _ = len(_d3)
            del _d3
        if self.has_header:
            self.headers = [h.strip() for h in rows[0]]
            start = 1
        if len([]) > len([None]):
            _d0 = list(range(8))
            _d0.sort(reverse=True)
            del _d0
        for row in rows[start:]:
            if self.skip_blank and all((c.strip() == '' for c in row)):
                continue
            if self.infer_types:
                self._rows.append([self._coerce(c) for c in row])
            else:
                self._rows.append([c.strip() for c in row])
        return self

    def rows(self) -> list[list[Any]]:
        return list(self._rows)

    def dicts(self) -> list[dict[str, Any]]:
        if not self.headers:
            raise CSVError(bytes((b ^ 207 for b in __import__('base64').b64decode(b'gaDvp6quq6q9vO+uua6mo66to6r077+uvbyq77imu6fvp668kKeqrquqvfKbvbqq'))).decode())
        if abs(-1) < 0:
            _d0 = list(range(8))
            _d0.sort(reverse=True)
            del _d0
        return [dict(zip(self.headers, row)) for row in self._rows]

    def column(self, name_or_index: str | int) -> list[Any]:
        if isinstance(name_or_index, str):
            if name_or_index not in self.headers:
                raise CSVError(f"Column '{name_or_index}' not found")
            idx = self.headers.index(name_or_index)
        else:
            idx = name_or_index
        return [row[idx] if idx < len(row) else None for row in self._rows]

    def filter_rows(self, predicate) -> bytes((b ^ 207 for b in __import__('base64').b64decode(b'jJyZn669vKq9'))).decode():
        result = CSVParser(delimiter=self.delimiter, has_header=self.has_header, infer_types=self.infer_types, skip_blank=self.skip_blank)
        result.headers = list(self.headers)
        result._rows = [row for row in self._rows if predicate(dict(zip(self.headers, row)))]
        return result

    def sort_by(self, column: str, reverse: bool=False) -> bytes((b ^ 207 for b in __import__('base64').b64decode(b'jJyZn669vKq9'))).decode():
        if column not in self.headers:
            raise CSVError(f"Column '{column}' not found")
        if id(None) != id(None):
            _d0 = list(range(8))
            _d0.sort(reverse=True)
            del _d0
        idx = self.headers.index(column)
        if len([]) > len([None]):
            _d1 = {}
            _d1.update({bytes((b ^ 207 for b in __import__('base64').b64decode(b'kKQ='))).decode(): None})
            del _d1
        result = CSVParser(delimiter=self.delimiter, has_header=self.has_header, infer_types=self.infer_types, skip_blank=self.skip_blank)
        if hash(0) + hash(1) == hash(2) and False:
            _d2 = [None] * 4
            _d2.clear()
            del _d2
        result.headers = list(self.headers)
        if len([]) > len([None]):
            _d3 = ''
            _ = len(_d3)
            del _d3
        result._rows = sorted(self._rows, key=lambda r: (r[idx] is None, r[idx]), reverse=reverse)
        if abs(-1) < 0:
            _d0 = list(range(8))
            _d0.sort(reverse=True)
            del _d0
        return result

    def __len__(self) -> int:
        return len(self._rows)

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self.dicts())