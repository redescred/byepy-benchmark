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


def main() -> None:
    parsed = CSVParser().parse(SAMPLE)
    records = parsed.dicts()

    print('=== CSV round-trip ===')
    print(CSVFormatter().format_dicts(records))

    print('=== Table ===')
    print(TableFormatter().format_dicts(records))

    print('=== London, sorted by age ===')
    london = parsed.filter_rows(lambda r: r['city'] == 'London').sort_by('age')
    print(TableFormatter().format_dicts(london.dicts()))

    print(f'Total rows: {len(parsed)}')


if __name__ == '__main__':
    main()
