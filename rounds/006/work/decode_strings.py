#!/usr/bin/env python3
"""Decode all base64+xor strings in code objects."""
import sys
import base64
import dis
import types
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from extract import get_code


def find_xor_byte(code):
    for instr in dis.get_instructions(code):
        if instr.opname == 'LOAD_SMALL_INT' and isinstance(instr.argval, int) and 0 <= instr.argval < 256:
            return instr.argval
        if instr.opname == 'LOAD_CONST' and isinstance(instr.argval, int) and 0 <= instr.argval < 256:
            return instr.argval
    return None


def walk_decode(code, indent=0, accum=None):
    if accum is None:
        accum = {}
    pad = '  ' * indent
    consts = code.co_consts
    instrs = list(dis.get_instructions(code))
    print(f"{pad}--- {code.co_name} (line {code.co_firstlineno}) ---")
    print(f"{pad}varnames: {code.co_varnames}")
    print(f"{pad}names: {code.co_names}")

    # find string decodings: look for pattern MAKE_FUNCTION → ... base64 → b64decode(LOAD_CONST <bytes>)
    # Track each LOAD_CONST <bytes> paired with a preceding MAKE_FUNCTION whose code has a XOR byte.
    last_xor = None
    for j, ins in enumerate(instrs):
        if ins.opname == 'MAKE_FUNCTION':
            prev = instrs[j-1]
            if prev.opname == 'LOAD_CONST' and isinstance(prev.argval, types.CodeType):
                xb = find_xor_byte(prev.argval)
                if xb is not None:
                    last_xor = xb
        elif ins.opname == 'LOAD_CONST' and isinstance(ins.argval, bytes) and last_xor is not None:
            # try to b64decode + xor
            try:
                raw = base64.b64decode(ins.argval)
                decoded = bytes(b ^ last_xor for b in raw).decode('utf-8', errors='replace')
                print(f"{pad}  b'{ins.argval.decode()}' xor {last_xor} = {decoded!r}")
                last_xor = None
            except Exception:
                pass

    for c in consts:
        if isinstance(c, types.CodeType):
            walk_decode(c, indent + 1, accum)
    return accum


if __name__ == '__main__':
    p = Path(sys.argv[1])
    code, src = get_code(p)
    walk_decode(code)
