import csv
import io
from typing import Any, Iterator

from .parser import CSVParser, CSVError
from .formatter import CSVFormatter, TableFormatter

__version__ = '0.1.0'
__all__ = ['CSVParser', 'CSVError', 'CSVFormatter', 'TableFormatter']

SAMPLE = (
    'name,age,city,active\n'
    'Alice,30,London,true\n'
    'Bob,25,Manchester,false\n'
    'Carol,35,London,true\n'
    'Dave,28,Edinburgh,true\n'
)


def main() -> None:
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
    main()
