"""Analyze a stage-2 marshal code object: dump structure + decoded strings + builtin lookup.

This gives me everything needed to manually reconstruct clean Python source.
"""
import ast
import dis
import marshal
import sys
import zlib
import lzma
from pathlib import Path

from stage2 import stage1, stage2
from strings import collect_strings, lambda_xor_params, decode_string


def show(code, indent=0, parent_strings=None):
    """Recursive structure dump."""
    pad = '  ' * indent
    print(f'{pad}<code {code.co_name} argcount={code.co_argcount} flags={hex(code.co_flags)}>')
    print(f'{pad}  varnames: {code.co_varnames}')
    print(f'{pad}  freevars: {code.co_freevars}')
    print(f'{pad}  cellvars: {code.co_cellvars}')
    print(f'{pad}  names: {code.co_names}')
    print(f'{pad}  consts (excluding code):')
    for c in code.co_consts:
        if hasattr(c, 'co_code'):
            continue
        print(f'{pad}    {c!r}')
    # Process child code objects
    for c in code.co_consts:
        if hasattr(c, 'co_code'):
            show(c, indent+1)


def all_strings(code, out=None):
    """Walk down code tree collecting all decoded obfuscated strings."""
    if out is None:
        out = {}
    instrs = list(dis.get_instructions(code))
    for i, ins in enumerate(instrs):
        if ins.opname == 'MAKE_FUNCTION':
            prev = instrs[i-1]
            if prev.opname == 'LOAD_CONST' and hasattr(prev.argval, 'co_code'):
                inner_code = prev.argval
                first_op = next(dis.get_instructions(inner_code), None)
                if first_op is None or first_op.opname != 'RETURN_GENERATOR':
                    continue
                params = lambda_xor_params(inner_code)
                if len(params) < 3:
                    continue
                c, m, a = params
                # Look for the next LOAD_CONST that is a string (hex)
                for j in range(i+1, min(i+15, len(instrs))):
                    if instrs[j].opname == 'LOAD_CONST' and isinstance(instrs[j].argval, str):
                        hex_str = instrs[j].argval
                        try:
                            decoded = decode_string(hex_str, c, m, a)
                        except Exception:
                            continue
                        out[hex_str] = decoded
                        break
    # recurse into child code objects (but skip the generator lambdas themselves)
    for c in code.co_consts:
        if hasattr(c, 'co_code'):
            first_op = next(dis.get_instructions(c), None)
            if first_op and first_op.opname == 'RETURN_GENERATOR':
                continue
            all_strings(c, out)
    return out


if __name__ == '__main__':
    for p in sys.argv[1:]:
        path = Path(p)
        src1 = stage1(path)
        code, lookup, gname = stage2(src1)
        print(f'=== {path} ===')
        print(f'globals lookup: {lookup}')
        print()
        print('--- structure ---')
        show(code)
        print()
        print('--- strings ---')
        for hex_str, decoded in all_strings(code).items():
            print(f'  {hex_str[:40]!s:42} -> {decoded!r}')
        print()
        print('--- full dis ---')
        dis.dis(code)
        print()
