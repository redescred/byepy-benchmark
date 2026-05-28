"""Entry point: python -m csvkit"""
from .formatter import CSVFormatter, TableFormatter
from .parser import CSVParser


SAMPLE = (
    'name,age,city,active\n'
    'Alice,30,London,true\n'
    'Bob,25,Manchester,false\n'
    'Carol,35,London,true\n'
    'Dave,28,Edinburgh,true\n'
)


def main():
    parser = CSVParser().parse(SAMPLE)

    print('=== CSV round-trip ===')
    print(CSVFormatter().format_dicts(parser.dicts()))

    print('=== Table ===')
    print(TableFormatter().format_dicts(parser.dicts()))

    print('=== London, sorted by age ===')
    filtered = parser.filter_rows(lambda r: r['city'] == 'London').sort_by('age')
    print(TableFormatter().format_dicts(filtered.dicts()))

    print(f'Total rows: {len(parser)}')


if __name__ == '__main__':
    main()
