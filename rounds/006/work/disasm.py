#!/usr/bin/env python3
"""Dump all code objects + dis + consts of a recovered file."""
import sys
import dis
import types
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from extract import get_code


def dump_code(code, prefix='', indent=0):
    pad = '  ' * indent
    print(f"{pad}=== Code object: {prefix}{code.co_name} ===")
    print(f"{pad}argcount={code.co_argcount} posonly={code.co_posonlyargcount} kwonly={code.co_kwonlyargcount}")
    print(f"{pad}varnames={code.co_varnames}")
    print(f"{pad}names={code.co_names}")
    print(f"{pad}freevars={code.co_freevars}")
    print(f"{pad}cellvars={code.co_cellvars}")
    print(f"{pad}flags={code.co_flags:#x}")
    print(f"{pad}consts:")
    for i, c in enumerate(code.co_consts):
        if isinstance(c, types.CodeType):
            print(f"{pad}  [{i}] <code {c.co_name}>")
        else:
            print(f"{pad}  [{i}] {c!r}")
    print(f"{pad}--- bytecode ---")
    dis.dis(code, file=sys.stdout)
    print()

    # recurse
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            dump_code(c, prefix=f"{prefix}{code.co_name}.", indent=indent + 1)


if __name__ == '__main__':
    p = Path(sys.argv[1])
    code, src = get_code(p)
    dump_code(code)
