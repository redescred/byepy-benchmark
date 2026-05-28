from .formatter import CSVFormatter, TableFormatter
from .parser import CSVParser

SAMPLE = 'name,age,city,active\nAlice,30,London,true\nBob,25,Manchester,false\nCarol,35,London,true\nDave,28,Edinburgh,true\n'


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
