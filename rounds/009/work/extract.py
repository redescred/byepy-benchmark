"""Static extractor for round 008 byepy obfuscation.

Stage 1: zlib + XOR -> Stage 2 source (we read _D, _K from AST and decrypt without exec).
Stage 2: lzma + XOR -> marshal'd code object, plus _ft (builtins) and _c (ints) tables built in plain Python.

We extract:
 - code object (decrypt + marshal.loads)
 - _ft mapping: dispatch_key -> builtin name
 - _c mapping: const_key -> int value
 - the table varnames (ft_varname, cv_varname)
"""
import ast
import marshal
import lzma
import zlib
import sys
from pathlib import Path


def parse_literal(node):
    return ast.literal_eval(node)


def extract_assigns(src):
    tree = ast.parse(src)
    out = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = stmt.value
    return out


def decrypt_xor16(data, key):
    return bytes(b ^ key[i % 16] for i, b in enumerate(data))


def stage1_decode(stage1_src):
    assigns = extract_assigns(stage1_src)
    D = parse_literal(assigns["_D"])
    K = parse_literal(assigns["_K"])
    return zlib.decompress(decrypt_xor16(D, K)).decode("utf-8")


def stage2_decode(stage2_src):
    tree = ast.parse(stage2_src)

    D2 = None
    K2 = None
    ft_varname = None
    cv_varname = None
    ft_dict = {}
    c_dict = {}

    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            t = stmt.targets[0]
            if isinstance(t, ast.Name):
                if t.id == "_D2":
                    D2 = parse_literal(stmt.value)
                    continue
                if t.id == "_K2":
                    K2 = parse_literal(stmt.value)
                    continue
            if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name):
                name = t.value.id
                key_int = parse_literal(t.slice)
                if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, int):
                    c_dict[key_int] = stmt.value.value
                    cv_varname = name
                else:
                    builtin_name = decode_ft_value(stmt.value)
                    ft_dict[key_int] = builtin_name
                    ft_varname = name

    raw = lzma.decompress(decrypt_xor16(D2, K2))
    code_obj = marshal.loads(raw)
    return {
        "code": code_obj,
        "ft": ft_dict,
        "c": c_dict,
        "ft_varname": ft_varname,
        "cv_varname": cv_varname,
    }


def decode_ft_value(node):
    # node: getattr(__import__('builtins'), <decode_call>)
    # decode_call: bytes(<genexp>).decode()
    # genexp.iter: enumerate(bytes.fromhex(<hex_str>))
    assert isinstance(node, ast.Call)
    decode_call = node.args[1]
    bytes_call = decode_call.func.value
    genexp = bytes_call.args[0]
    enumerate_call = genexp.generators[0].iter
    fromhex_call = enumerate_call.args[0]
    hex_arg = fromhex_call.args[0].value
    enc_bytes = bytes.fromhex(hex_arg)
    elt = genexp.elt
    K = _extract_K_from_xor_expr(elt.right)
    raw = bytes((b ^ ((K + i * 11 + 5) & 0xFF)) for i, b in enumerate(enc_bytes))
    return raw.decode("utf-8")


def _extract_K_from_xor_expr(node):
    consts = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, int):
            consts.append(sub.value)
    candidates = [c for c in consts if c not in (11, 5, 255)]
    if not candidates:
        raise ValueError("Could not locate K constant in decode expression")
    return candidates[0]


def extract_from_file(path):
    src = Path(path).read_text()
    s2 = stage1_decode(src)
    info = stage2_decode(s2)
    return info, s2


if __name__ == "__main__":
    info, s2 = extract_from_file(sys.argv[1])
    print(f"ft_varname={info['ft_varname']}")
    print(f"cv_varname={info['cv_varname']}")
    print(f"ft entries: {len(info['ft'])}")
    print(f"c entries:  {len(info['c'])}")
    print(f"code: {info['code']}")
    print(f"co_consts: {info['code'].co_consts}")
    print(f"co_names:  {info['code'].co_names}")
    print(f"co_varnames: {info['code'].co_varnames}")
