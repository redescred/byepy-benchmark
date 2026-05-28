#!/usr/bin/env python3
"""Decode the _ft dispatch table from a code object.

The module-level code builds: {key1: builtin1, key2: builtin2, ...}
Each builtin is constructed as:
  getattr(__import__('builtins'), bytes((xor_byte for _ in tup)).decode())
The XOR generator at LOAD_CONST <code> XORs each tuple element with a const byte.
"""
import sys
import types
import dis
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from extract import get_code


def decode_xor_gen(code):
    """Pull the constant XOR byte out of a generator-lambda code object."""
    for instr in dis.get_instructions(code):
        if instr.opname == 'LOAD_SMALL_INT' and isinstance(instr.argval, int) and 0 <= instr.argval < 256:
            # this is the XOR byte
            return instr.argval
        if instr.opname == 'LOAD_CONST' and isinstance(instr.argval, int) and 0 <= instr.argval < 256:
            return instr.argval
    raise ValueError("no xor byte")


def build_ft(module_code):
    """Walk module bytecode and return {int_key: builtin_name}.

    The pattern: LOAD_CONST <key>, ..., LOAD_CONST <lambda>, MAKE_FUNCTION,
                 LOAD_CONST <tup>, ..., then a BUILD_MAP at the end.
    """
    consts = module_code.co_consts
    # Parse instruction stream sequentially. Each builtin entry is a fixed pattern:
    #   LOAD_CONST <int_key>          (the dict key)
    #   ... (getattr(__import__('builtins'), bytes(map(generator, tup)).decode())
    #   LOAD_CONST <gen_lambda_code>  (provides the XOR generator over tup)
    #   ...
    #   LOAD_CONST <tup>              (the encoded bytes tuple)
    # We can pair up: scan for LOAD_CONST <int>, then look ahead for the gen code and tup.
    instrs = list(dis.get_instructions(module_code))
    # Find the BUILD_MAP that corresponds to the _ft table: largest BUILD_MAP in module.
    last_bm = -1
    last_bm_size = 0
    for idx, ins in enumerate(instrs):
        if ins.opname == 'BUILD_MAP' and isinstance(ins.argval, int) and ins.argval > last_bm_size:
            last_bm = idx
            last_bm_size = ins.argval
    end_idx = last_bm if last_bm > -1 else len(instrs)
    entries = []
    i = 0
    while i < end_idx:
        ins = instrs[i]
        # spot keys: small int constants used as dict keys are loaded right before getattr
        # Easier: walk for MAKE_FUNCTION patterns
        if ins.opname == 'MAKE_FUNCTION':
            # the LOAD_CONST right before MAKE_FUNCTION is the generator code
            gen_code = instrs[i-1].argval
            if not isinstance(gen_code, types.CodeType):
                i += 1
                continue
            xor_byte = decode_xor_gen(gen_code)
            # the tup is next LOAD_CONST that is a tuple of ints
            tup = None
            j = i + 1
            while j < len(instrs):
                op = instrs[j]
                if op.opname == 'LOAD_CONST' and isinstance(op.argval, tuple):
                    tup = op.argval
                    break
                if op.opname in ('LOAD_SMALL_INT',):
                    # LIST_EXTEND-style: collect contiguous LOAD_SMALL_INT into a tuple
                    parts = []
                    k = j
                    while k < len(instrs) and instrs[k].opname == 'LOAD_SMALL_INT':
                        parts.append(instrs[k].argval)
                        k += 1
                    if instrs[k].opname == 'BUILD_LIST':
                        tup = tuple(parts)
                        break
                if op.opname == 'BUILD_MAP':
                    break
                j += 1
            if tup is None:
                i += 1
                continue
            # the key is the LOAD_CONST before the entire getattr sequence
            # walk backwards from i to find the matching key
            k = i - 1
            depth = 0
            # Pattern: LOAD_CONST <key>, LOAD_NAME getattr, PUSH_NULL, LOAD_NAME __import__, PUSH_NULL, LOAD_CONST 'builtins', CALL, ...
            # The key comes right before LOAD_NAME getattr. Walk back to find LOAD_NAME getattr.
            while k >= 0:
                if instrs[k].opname == 'LOAD_NAME' and instrs[k].argval == 'getattr':
                    # the LOAD_CONST right before is the key
                    key = instrs[k-1].argval
                    break
                k -= 1
            name = bytes(b ^ xor_byte for b in tup).decode()
            entries.append((key, name))
            i = j + 1
        else:
            i += 1
    return dict(entries)


if __name__ == '__main__':
    p = Path(sys.argv[1])
    code, src = get_code(p)
    ft = build_ft(code)
    for k, v in ft.items():
        print(f"{k}: {v}")
