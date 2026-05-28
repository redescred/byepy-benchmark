import csv
import io
from typing import Any, Iterator

class CSVError(Exception):
    pass

class CSVParser:
    BOOL_TRUE = {bytes((b ^ 177 for b in __import__('base64').b64decode(b'xcPE1A=='))).decode(), bytes((b ^ 177 for b in __import__('base64').b64decode(b'yNTC'))).decode(), bytes((b ^ 177 for b in __import__('base64').b64decode(b'gA=='))).decode(), bytes((b ^ 177 for b in __import__('base64').b64decode(b'3t8='))).decode()}
    BOOL_FALSE = {bytes((b ^ 177 for b in __import__('base64').b64decode(b'19DdwtQ='))).decode(), bytes((b ^ 177 for b in __import__('base64').b64decode(b'394='))).decode(), bytes((b ^ 177 for b in __import__('base64').b64decode(b'gQ=='))).decode(), bytes((b ^ 177 for b in __import__('base64').b64decode(b'3tfX'))).decode()}

    def __init__(self, delimiter: str=bytes((b ^ 177 for b in __import__('base64').b64decode(b'nQ=='))).decode(), has_header: bool=True, infer_types: bool=True, skip_blank: bool=True) -> None:
        self.delimiter = delimiter
        if type(None) is type(0):
            _d0 = list(range(8))
            _d0.sort(reverse=True)
            del _d0
        self.has_header = has_header
        self.infer_types = infer_types
        if abs(-1) < 0:
            _ = type(delimiter)
            del _
        self.skip_blank = skip_blank
        if False and True:
            _d3 = ''
            _ = len(_d3)
            del _d3
        self.headers: list[str] = []
        if 0 > 1:
            _ = id(infer_types)
            del _
        self._rows: list[list[Any]] = []

    def _coerce(self, value: str) -> Any:
        v = value.strip()
        if len([]) > len([None]):
            _ = type(value)
            del _
        if v == '':
            return None
        if False and True:
            _ = id(value)
            del _
        if v.lower() in self.BOOL_TRUE:
            return True
        if v.lower() in self.BOOL_FALSE:
            return False
        if hash(0) + hash(1) == hash(2) and False:
            _d3 = ''
            _ = len(_d3)
            del _d3
        try:
            return int(v)
        except ValueError:
            pass
        if abs(-1) < 0:
            _ = bool(value)
            del _
        try:
            return float(v)
        except ValueError:
            pass
        if type(None) is type(0):
            _d5 = bytes(4)
            _ = len(_d5)
            del _d5
        return v

    def parse(self, text: str) -> bytes((b ^ 177 for b in __import__('base64').b64decode(b'8uLn4dDDwtTD'))).decode():
        reader = csv.reader(io.StringIO(text), delimiter=self.delimiter)
        if hash(0) + hash(1) == hash(2) and False:
            _d0 = list(range(8))
            _d0.sort(reverse=True)
            del _d0
        rows = list(reader)
        if not rows:
            return self
        if type(None) is type(0):
            _ = id(text)
            del _
        start = 0
        if abs(-1) < 0:
            _ = bool(text)
            del _
        if self.has_header:
            self.headers = [h.strip() for h in rows[0]]
            start = 1
        if __import__(bytes((b ^ 177 for b in __import__('base64').b64decode(b'wsjC'))).decode()).version_info.major < 2:
            _d4 = set()
            _d4.add(0)
            _d4.discard(0)
        for row in rows[start:]:
            if self.skip_blank and all((c.strip() == '' for c in row)):
                continue
            if self.infer_types:
                self._rows.append([self._coerce(c) for c in row])
            else:
                self._rows.append([c.strip() for c in row])
        if id(None) != id(None):
            _ = type(text)
            del _
        return self

    def rows(self) -> list[list[Any]]:
        return list(self._rows)

    def dicts(self) -> list[dict[str, Any]]:
        if not self.headers:
            raise CSVError(bytes((b ^ 177 for b in __import__('base64').b64decode(b'/96R2dTQ1dTDwpHQx9DY3dDT3dSKkcHQw8LUkcbYxdmR2dDC7tnU0NXUw4zlw8TU'))).decode())
        if __import__(bytes((b ^ 177 for b in __import__('base64').b64decode(b'wsjC'))).decode()).version_info.major < 2:
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
        if type(None) is type(0):
            _d0 = list(range(8))
            _d0.sort(reverse=True)
            del _d0
        return [row[idx] if idx < len(row) else None for row in self._rows]

    def filter_rows(self, predicate) -> bytes((b ^ 177 for b in __import__('base64').b64decode(b'8uLn4dDDwtTD'))).decode():
        result = CSVParser(delimiter=self.delimiter, has_header=self.has_header, infer_types=self.infer_types, skip_blank=self.skip_blank)
        if 0 > 1:
            _ = type(predicate)
            del _
        result.headers = list(self.headers)
        if len([]) > len([None]):
            _d1 = {}
            _d1.update({bytes((b ^ 177 for b in __import__('base64').b64decode(b'7to='))).decode(): None})
            del _d1
        result._rows = [row for row in self._rows if predicate(dict(zip(self.headers, row)))]
        if hash(0) + hash(1) == hash(2) and False:
            _d2 = [None] * 4
            _d2.clear()
            del _d2
        return result

    def sort_by(self, column: str, reverse: bool=False) -> bytes((b ^ 177 for b in __import__('base64').b64decode(b'8uLn4dDDwtTD'))).decode():
        if column not in self.headers:
            raise CSVError(f"Column '{column}' not found")
        idx = self.headers.index(column)
        if type(None) is type(0):
            _d1 = {}
            _d1.update({bytes((b ^ 177 for b in __import__('base64').b64decode(b'7to='))).decode(): None})
            del _d1
        result = CSVParser(delimiter=self.delimiter, has_header=self.has_header, infer_types=self.infer_types, skip_blank=self.skip_blank)
        if id(None) != id(None):
            _ = id(reverse)
            del _
        result.headers = list(self.headers)
        if hash(0) + hash(1) == hash(2) and False:
            _d3 = ''
            _ = len(_d3)
            del _d3
        result._rows = sorted(self._rows, key=lambda r: (r[idx] is None, r[idx]), reverse=reverse)
        if abs(-1) < 0:
            _ = bool(column)
            del _
        return result

    def __len__(self) -> int:
        return len(self._rows)

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self.dicts())