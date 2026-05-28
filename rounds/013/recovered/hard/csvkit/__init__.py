"""csvkit — CSV parser and table formatter."""

__all__ = ['CSVParser', 'CSVError', 'CSVFormatter', 'TableFormatter']
__version__ = '0.1.0'

from .parser import CSVParser, CSVError
from .formatter import CSVFormatter, TableFormatter
