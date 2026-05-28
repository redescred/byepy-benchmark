"""Entry point: python -m csvkit"""

from .formatter import CSVFormatter, TableFormatter
from .parser import CSVParser

SAMPLE = 'name,age,city,active\nAlice,30,London,true\nBob,25,Manchester,false\nCarol,35,London,true\nDave,28,Edinburgh,true\n'


def main():
    lllIIlIIIIlIIIl = CSVParser().parse(SAMPLE)
    lllIIIIIlllllIl = lllIIlIIIIlIIIl.dicts()
    print('=== CSV round-trip ===')
    print(CSVFormatter().format_dicts(lllIIIIIlllllIl))
    print('=== Table ===')
    print(TableFormatter().format_dicts(lllIIIIIlllllIl))
    print('=== London, sorted by age ===')
    llIllIllIIllIll = lllIIlIIIIlIIIl.filter_rows(lambda r: r['city'] == 'London').sort_by('age')
    print(TableFormatter().format_dicts(llIllIllIIllIll.dicts()))
    print(f'Total rows: {len(lllIIlIIIIlIIIl)}')


if __name__ == '__main__':
    main()
