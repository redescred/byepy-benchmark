"""CSV and table output formatters."""
import csv
import io
from typing import Any


class CSVFormatter:

    def __init__(self, delimiter=',', quoting=csv.QUOTE_MINIMAL):
        self.delimiter = delimiter
        self.quoting = quoting

    def format(self, headers, rows):
        llIIIIIllllIIlI = io.StringIO()
        lllIlllIlllIlll = csv.writer(llIIIIIllllIIlI, delimiter=self.delimiter, quoting=self.quoting)
        if headers:
            lllIlllIlllIlll.writerow(headers)
        for llIIllIlIIIllIl in rows:
            lllIlllIlllIlll.writerow([str(llIllIIlIllIlIl) if llIllIIlIllIlIl is not None else '' for llIllIIlIllIlIl in llIIllIlIIIllIl])
        return llIIIIIllllIIlI.getvalue()

    def format_dicts(self, records):
        if not records:
            return ''
        lIIIIIlllllllII = list(records[0].keys())
        llIlIlIIIlIlIll = [[lllIIIIlIlIlIIl.get(lIllllllIIIlIII) for lIllllllIIIlIII in lIIIIIlllllllII] for lllIIIIlIlIlIIl in records]
        return self.format(lIIIIIlllllllII, llIlIlIIIlIlIll)


class TableFormatter:

    def __init__(self, padding=1, border=True):
        self.padding = padding
        self.border = border

    def _col_widths(self, headers, rows):
        lIIllIIlIllIlll = [len(str(lllllIlIIIlIlIl)) for lllllIlIIIlIlIl in headers]
        for llIllllllIllIll in rows:
            for lIIIlIIIIllIIIl, lIlIllllllllIll in enumerate(llIllllllIllIll):
                if lIIIlIIIIllIIIl < len(lIIllIIlIllIlll):
                    lIIllIIlIllIlll[lIIIlIIIIllIIIl] = max(lIIllIIlIllIlll[lIIIlIIIIllIIIl], len(str(lIlIllllllllIll) if lIlIllllllllIll is not None else ''))
        return lIIllIIlIllIlll

    def _pad(self, value, width):
        llIIIlIIllIIlII = str(value) if value is not None else ''
        return llIIIlIIllIIlII.ljust(width)

    def format(self, headers, rows):
        llIIIlIllIllllI = self._col_widths(headers, rows)
        llIlIllllIllllI = ' ' * self.padding
        lIIlIIIlIllIlll = '+' + '+'.join(('-' * (lIllIIlllIIIIIl + self.padding * 2) for lIllIIlllIIIIIl in llIIIlIllIllllI)) + '+'
        llIlIIllIIllIlI = []
        if self.border:
            llIlIIllIIllIlI.append(lIIlIIIlIllIlll)
        lIlIIlIlIIlIIlI = '|' + '|'.join((llIlIllllIllllI + self._pad(llllIlIIlIllIIl, llIIIlIllIllllI[lIllIIlllIIIIIl]) + llIlIllllIllllI for lIllIIlllIIIIIl, llllIlIIlIllIIl in enumerate(headers))) + '|'
        llIlIIllIIllIlI.append(lIlIIlIlIIlIIlI)
        if self.border:
            llIlIIllIIllIlI.append(lIIlIIIlIllIlll)
        for lllIlIIIlIlIlll in rows:
            llIIIllIlIIIllI = []
            for llIIllIIlIIllIl, llIlIlIlIIllIlI in enumerate(llIIIlIllIllllI):
                llIlIllIllIIlIl = lllIlIIIlIlIlll[llIIllIIlIIllIl] if llIIllIIlIIllIl < len(lllIlIIIlIlIlll) else ''
                llIIIllIlIIIllI.append(llIlIllllIllllI + self._pad(llIlIllIllIIlIl, llIlIlIlIIllIlI) + llIlIllllIllllI)
            llIlIIllIIllIlI.append('|' + '|'.join(llIIIllIlIIIllI) + '|')
        if self.border:
            llIlIIllIIllIlI.append(lIIlIIIlIllIlll)
        return '\n'.join(llIlIIllIIllIlI)

    def format_dicts(self, records):
        if not records:
            return '(empty)'
        lIIIllIIIIlIlll = list(records[0].keys())
        lllIllIIIIIIIll = [[lIlIlIllIllllll.get(llIIIllIIlllIll) for llIIIllIIlllIll in lIIIllIIIIlIlll] for lIlIlIllIllllll in records]
        return self.format(lIIIllIIIIlIlll, lllIllIIIIIIIll)
