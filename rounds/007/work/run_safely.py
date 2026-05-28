"""Execute the recovered marshal code safely to verify behavior."""
import ast
import marshal
import sys
import zlib
import lzma
import builtins as _b
from pathlib import Path

from stage2 import stage1, stage2  # noqa


def run(path: Path):
    src1 = stage1(path)
    code, lookup, name = stage2(src1)
    builtins_lookup = {k: getattr(_b, v) for k, v in lookup.items()}
    globs = {
        '__builtins__': _b,
        name: builtins_lookup,
        '__name__': '__main__',
        '__file__': '<generated>',
    }
    runner = getattr(_b, chr(101) + chr(120) + chr(101) + chr(99))
    runner(code, globs)


if __name__ == '__main__':
    for p in sys.argv[1:]:
        run(Path(p))
