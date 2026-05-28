__import__('base64').b64decode(b'Q1NWIHBhcnNlciB3aXRoIHR5cGUgaW5mZXJlbmNlIGFuZCBlcnJvciBoYW5kbGluZy4=').decode()
import csv
import io
from typing import Any, Iterator

class CSVError(Exception):
    __import__('base64').b64decode(b'UmFpc2VkIGZvciBtYWxmb3JtZWQgb3IgdW5yZWFkYWJsZSBDU1YgaW5wdXQu').decode()

class CSVParser:
    __import__('base64').b64decode(b'UGFyc2UgQ1NWIHRleHQgaW50byB0eXBlZCByb3dzIHdpdGggb3B0aW9uYWwgaGVhZGVyIGhhbmRsaW5nLg==').decode()
    BOOL_TRUE = {__import__('base64').b64decode(b'dHJ1ZQ==').decode(), __import__('base64').b64decode(b'eWVz').decode(), __import__('base64').b64decode(b'MQ==').decode(), __import__('base64').b64decode(b'b24=').decode()}
    BOOL_FALSE = {__import__('base64').b64decode(b'ZmFsc2U=').decode(), __import__('base64').b64decode(b'bm8=').decode(), __import__('base64').b64decode(b'MA==').decode(), __import__('base64').b64decode(b'b2Zm').decode()}

    def __init__(self, delimiter: str=__import__('base64').b64decode(b'LA==').decode(), has_header: bool=True, infer_types: bool=True, skip_blank: bool=True) -> None:
        self.delimiter = delimiter
        self.has_header = has_header
        self.infer_types = infer_types
        self.skip_blank = skip_blank
        self.headers: list[str] = []
        self._rows: list[list[Any]] = []

    def _coerce(self, value: str) -> Any:
        __import__('base64').b64decode(b'QXR0ZW1wdCB0byBjb252ZXJ0IGEgc3RyaW5nIHRvIGludCwgZmxvYXQsIGJvb2wsIG9yIGxlYXZlIGFzIHN0ci4=').decode()
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

    def parse(self, text: str) -> __import__('base64').b64decode(b'Q1NWUGFyc2Vy').decode():
        __import__('base64').b64decode(b'UGFyc2UgQ1NWIHRleHQuIFJldHVybnMgc2VsZiBmb3IgY2hhaW5pbmcu').decode()
        reader = csv.reader(io.StringIO(text), delimiter=self.delimiter)
        rows = list(reader)
        if not rows:
            return self
        start = 0
        if self.has_header:
            self.headers = [h.strip() for h in rows[0]]
            start = 1
        for row in rows[start:]:
            if self.skip_blank and all((c.strip() == '' for c in row)):
                continue
            if self.infer_types:
                self._rows.append([self._coerce(c) for c in row])
            else:
                self._rows.append([c.strip() for c in row])
        return self

    def rows(self) -> list[list[Any]]:
        __import__('base64').b64decode(b'UmV0dXJuIGFsbCBwYXJzZWQgcm93cyBhcyBsaXN0cy4=').decode()
        return list(self._rows)

    def dicts(self) -> list[dict[str, Any]]:
        __import__('base64').b64decode(b'UmV0dXJuIHJvd3MgYXMgZGljdHMga2V5ZWQgYnkgaGVhZGVyLiBSYWlzZXMgaWYgbm8gaGVhZGVycy4=').decode()
        if not self.headers:
            raise CSVError(__import__('base64').b64decode(b'Tm8gaGVhZGVycyBhdmFpbGFibGU7IHBhcnNlIHdpdGggaGFzX2hlYWRlcj1UcnVl').decode())
        return [dict(zip(self.headers, row)) for row in self._rows]

    def column(self, name_or_index: str | int) -> list[Any]:
        __import__('base64').b64decode(b'RXh0cmFjdCBhIHNpbmdsZSBjb2x1bW4gYnkgaGVhZGVyIG5hbWUgb3IgaW5kZXgu').decode()
        if isinstance(name_or_index, str):
            if name_or_index not in self.headers:
                raise CSVError(f"Column '{name_or_index}' not found")
            idx = self.headers.index(name_or_index)
        else:
            idx = name_or_index
        return [row[idx] if idx < len(row) else None for row in self._rows]

    def filter_rows(self, predicate) -> __import__('base64').b64decode(b'Q1NWUGFyc2Vy').decode():
        __import__('base64').b64decode(b'UmV0dXJuIGEgbmV3IENTVlBhcnNlciBjb250YWluaW5nIG9ubHkgcm93cyB3aGVyZSBwcmVkaWNhdGUoZGljdCkgaXMgVHJ1ZS4=').decode()
        result = CSVParser(delimiter=self.delimiter, has_header=self.has_header, infer_types=self.infer_types, skip_blank=self.skip_blank)
        result.headers = list(self.headers)
        result._rows = [row for row in self._rows if predicate(dict(zip(self.headers, row)))]
        return result

    def sort_by(self, column: str, reverse: bool=False) -> __import__('base64').b64decode(b'Q1NWUGFyc2Vy').decode():
        __import__('base64').b64decode(b'UmV0dXJuIGEgbmV3IENTVlBhcnNlciB3aXRoIHJvd3Mgc29ydGVkIGJ5IGEgY29sdW1uLg==').decode()
        if column not in self.headers:
            raise CSVError(f"Column '{column}' not found")
        idx = self.headers.index(column)
        result = CSVParser(delimiter=self.delimiter, has_header=self.has_header, infer_types=self.infer_types, skip_blank=self.skip_blank)
        result.headers = list(self.headers)
        result._rows = sorted(self._rows, key=lambda r: (r[idx] is None, r[idx]), reverse=reverse)
        return result

    def __len__(self) -> int:
        return len(self._rows)

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self.dicts())