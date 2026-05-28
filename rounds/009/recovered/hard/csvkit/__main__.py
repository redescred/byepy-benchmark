from .formatter import CSVFormatter, TableFormatter
from .parser import CSVParser, CSVError

__all__ = ['CSVParser', 'CSVError', 'CSVFormatter', 'TableFormatter']

__version__ = '0.1.0'

import csv

import io

from typing import Any

SAMPLE = 'name,age,city,active\nAlice,30,London,true\nBob,25,Manchester,false\nCarol,35,London,true\nDave,28,Edinburgh,true\n'

def demo():
    parser = CSVParser().parse(SAMPLE)
    records = parser.dicts()
    print('=== CSV round-trip ===')
    print(CSVFormatter().format_dicts(records))
    print('=== Table ===')
    print(TableFormatter().format_dicts(records))
    print('=== London, sorted by age ===')
    london_sorted = parser.filter_rows(lambda r: r['city'] == 'London').sort_by('age')
    print(TableFormatter().format_dicts(london_sorted.dicts()))
    print(f'Total rows: {len(parser)}')

if __name__ == '__main__':
    demo()
