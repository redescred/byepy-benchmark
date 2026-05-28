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
        lllllIIllIIIIIl = value.strip()
        if lllllIIllIIIIIl.lower() in self.BOOL_TRUE:
            return True
        if lllllIIllIIIIIl.lower() in self.BOOL_FALSE:
            return False
        try:
            return int(lllllIIllIIIIIl)
        except ValueError:
            pass
        try:
            return float(lllllIIllIIIIIl)
        except ValueError:
            pass
        return lllllIIllIIIIIl

    def parse(self, text):
        lIllIIIlIIIIlII = csv.reader(io.StringIO(text), delimiter=self.delimiter)
        lIlIlllIlIlllll = list(lIllIIIlIIIIlII)
        if not lIlIlllIlIlllll:
            return self
        llIllIlIIlllIlI = 0
        if self.has_header:
            self.headers = [llIlllllllIIlII.strip() for llIlllllllIIlII in lIlIlllIlIlllll[0]]
            llIllIlIIlllIlI = 1
        for llIIlIIIIlllIII in lIlIlllIlIlllll[llIllIlIIlllIlI:None]:
            if self.skip_blank:
                if all((lIllIIIIlIlIllI.strip() == '' for lIllIIIIlIlIllI in llIIlIIIIlllIII)):
                    continue
            if self.infer_types:
                self._rows.append([self._coerce(llIlIIIIlIIlllI) for llIlIIIIlIIlllI in llIIlIIIIlllIII])
            else:
                self._rows.append([llIlIIIIlIIlllI.strip() for llIlIIIIlIIlllI in llIIlIIIIlllIII])
        return self

    def rows(self):
        return list(self._rows)

    def dicts(self):
        if not self.headers:
            raise CSVError('No headers available; parse with has_header=True')
        return [dict(zip(self.headers, llIIlIllIlIIIlI)) for llIIlIllIlIIIlI in self._rows]

    def column(self, name_or_index):
        if isinstance(name_or_index, str):
            if name_or_index not in self.headers:
                raise CSVError(f"Column '{name_or_index}' not found")
            llIlIIIlIllIIII = self.headers.index(name_or_index)
        else:
            llIlIIIlIllIIII = name_or_index
        return [lIIlIIIIIIlllII[llIlIIIlIllIIII] if llIlIIIlIllIIII < len(lIIlIIIIIIlllII) else None for lIIlIIIIIIlllII in self._rows]

    def filter_rows(self, predicate):
        llllIlIlIlIlIlI = CSVParser(delimiter=self.delimiter, has_header=self.has_header, infer_types=self.infer_types, skip_blank=self.skip_blank)
        llllIlIlIlIlIlI.headers = list(self.headers)
        llllIlIlIlIlIlI._rows = [lllIllIIlllIIlI for lllIllIIlllIIlI in self._rows if predicate(dict(zip(self.headers, lllIllIIlllIIlI)))]
        return llllIlIlIlIlIlI

    def sort_by(self, column, reverse=False):
        if column not in self.headers:
            raise CSVError(f"Column '{column}' not found")
        lllllIIlllllllI = self.headers.index(column)
        lIIlIIIlIIlIlll = CSVParser(delimiter=self.delimiter, has_header=self.has_header, infer_types=self.infer_types, skip_blank=self.skip_blank)
        lIIlIIIlIIlIlll.headers = list(self.headers)
        lIIlIIIlIIlIlll._rows = sorted(self._rows, key=lambda r: (r[lllllIIlllllllI] is None, r[lllllIIlllllllI]), reverse=reverse)
        return lIIlIIIlIIlIlll

    def __len__(self):
        return len(self._rows)

    def __iter__(self):
        return iter(self.dicts())
