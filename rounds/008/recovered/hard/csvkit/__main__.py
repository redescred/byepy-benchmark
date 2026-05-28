"""Entry point: python -m csvkit"""
from .parser import CSVParser
from .formatter import CSVFormatter, TableFormatter


SAMPLE = (
    'name,age,city,active\n'
    'Alice,30,London,true\n'
    'Bob,25,Manchester,false\n'
    'Carol,35,London,true\n'
    'Dave,28,Edinburgh,true\n'
)


def main():
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
