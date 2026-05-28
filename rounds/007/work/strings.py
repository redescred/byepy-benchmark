"""Decode every obfuscated string literal in stage-2 code objects.

The string obfuscation pattern is uniform:
    bytes(_b ^ ((C + _i*M + A) & 255) for _i,_b in enumerate(bytes.fromhex(HEX))).decode()

In bytecode it appears as a MAKE_FUNCTION (lambda generator) followed by
LOAD_CONST hex_string, etc.

But the lambda's body holds the actual XOR constants. We disassemble lambdas
and extract (hex, C, M, A) tuples.
"""
import ast
import dis
import marshal
import sys
import zlib
import lzma
from pathlib import Path


def stage1(path: Path) -> str:
    tree = ast.parse(path.read_text())
    data = None
    key = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            if isinstance(tgt, ast.Name) and isinstance(node.value, ast.Constant):
                if tgt.id == '_D':
                    data = node.value.value
                elif tgt.id == '_K':
                    key = node.value.value
    xored = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return zlib.decompress(xored).decode()


def stage2_code(src: str):
    tree = ast.parse(src)
    data2 = None
    key2 = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            if isinstance(tgt, ast.Name) and isinstance(node.value, ast.Constant):
                if tgt.id == '_D2':
                    data2 = node.value.value
                elif tgt.id == '_K2':
                    key2 = node.value.value
    raw = lzma.decompress(bytes(b ^ key2[i % 16] for i, b in enumerate(data2)))
    return marshal.loads(raw)


def lambda_xor_params(code):
    """Inspect a generator lambda's bytecode to recover (M, A) XOR formula params.

    The lambda body computes: _b ^ ((C + _i*M + A) & 255)
    The generator function has the form:
        for _i, _b in iter:
            yield _b ^ ((C + _i*M + A) & 255)
    But C is passed-in via the iterator's enumerate-with-start? No: enumerate yields
    (_i starting at 0). The C is a LOAD_SMALL_INT in the lambda body.

    Inspecting the disassembly:
        LOAD_FAST_BORROW _b
        LOAD_SMALL_INT C      <- this is C
        LOAD_FAST_BORROW _i
        LOAD_SMALL_INT M      <- this is M
        BINARY_OP * (_i * M)
        BINARY_OP + (C + _i*M)
        LOAD_SMALL_INT A      <- this is A
        BINARY_OP + (((C + _i*M) + A))
        LOAD_SMALL_INT 255
        BINARY_OP &
        BINARY_OP ^

    Get the three small ints in order.
    """
    ints = []
    for instr in dis.get_instructions(code):
        if instr.opname == 'LOAD_SMALL_INT':
            ints.append(instr.arg)
    # ints should be [C, M, A, 255] (and maybe more if there's other code; we keep first 4)
    return ints[:3]


def decode_string(hex_str: str, c: int, m: int, a: int) -> str:
    raw = bytes.fromhex(hex_str)
    return bytes(b ^ ((c + i*m + a) & 255) for i, b in enumerate(raw)).decode()


def collect_strings(code, out=None):
    if out is None:
        out = {}
    # walk constants
    for const in code.co_consts:
        if hasattr(const, 'co_code'):
            collect_strings(const, out)
    # For each MAKE_FUNCTION followed by hex literal usage, we can find decoded strings.
    # Easier: look at consts list of inner-lambda generators; their parent code
    # has the hex_string constant we need. Scan all instructions in code looking
    # for the pattern: MAKE_FUNCTION ... LOAD_CONST hex_string ... CALL ... CALL ...
    # Actually we can scan all the lambda code objects for their xor parameters,
    # and pair them with hex strings from outer instructions.
    # The hex strings are LOAD_CONST values where the same line contains a MAKE_FUNCTION.
    # Simplest: for each MAKE_FUNCTION instruction, find next LOAD_CONST that looks like hex.
    instrs = list(dis.get_instructions(code))
    for i, ins in enumerate(instrs):
        if ins.opname == 'MAKE_FUNCTION':
            # the const that produced the code is at instrs[i-1].argval
            prev = instrs[i-1]
            if prev.opname == 'LOAD_CONST' and hasattr(prev.argval, 'co_code'):
                inner_code = prev.argval
                # Skip non-generator lambdas (the actual user functions). The XOR
                # generator lambdas have RETURN_GENERATOR as first instruction.
                first_op = next(dis.get_instructions(inner_code)).opname
                if first_op != 'RETURN_GENERATOR':
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
    return out


if __name__ == '__main__':
    for p in sys.argv[1:]:
        path = Path(p)
        src1 = stage1(path)
        code = stage2_code(src1)
        out = collect_strings(code)
        print(f'=== {path} ===')
        for hex_str, decoded in out.items():
            print(f'  {hex_str[:40]!s:42} -> {decoded!r}')
