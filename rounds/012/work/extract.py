"""Static extractor for round 010 byepy obfuscation.

Stage 1: zlib + XOR -> Stage 2 source (we read _D, _K from AST and decrypt without exec).
Stage 2: lzma + XOR -> marshal'd code object, plus _ft (builtins) and _c (ints) tables.

Round 10 changes handled here:
 - Stage 2 XOR uses position-dependent term: key[i%16] ^ ((i>>4) & 255)
 - _ft built via a for-loop over a list of (key, K, hex_str) triples
 - _c built via a for-loop over masked pairs: real_val = masked_val ^ _cm

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


def decrypt_xor16_pos(data, key):
    """Stage 2 round-10 XOR: key[i%16] ^ ((i>>4) & 255)."""
    return bytes(b ^ key[i % 16] ^ ((i >> 4) & 255) for i, b in enumerate(data))


def decrypt_xor16_s1_r12(data, key):
    """Round 12 Stage 1 XOR: key[i%16] ^ ((i*7+13) & 255)."""
    return bytes(b ^ key[i % 16] ^ ((i * 7 + 13) & 255) for i, b in enumerate(data))


def stage1_decode(stage1_src):
    """Decrypt Stage 1 to produce Stage 2 source text.

    Round 9/10: Stage 2 was a text string (zlib+XOR -> UTF-8).
    Round 11: Stage 2 is a compiled code object (zlib+XOR -> marshal bytes).
    Round 12: Stage 1 XOR changed to b ^ K[i%16] ^ ((i*7+13)&255).
    Detect which path by checking for 'marshal.loads' in the Stage 1 source.
    """
    assigns = extract_assigns(stage1_src)
    D = parse_literal(assigns["_D"])
    K = parse_literal(assigns["_K"])
    # Round 12 detection: the stage 1 source contains the new XOR formula
    if "_i*7+13" in stage1_src or "i*7+13" in stage1_src:
        raw = zlib.decompress(decrypt_xor16_s1_r12(D, K))
    else:
        raw = zlib.decompress(decrypt_xor16(D, K))

    if "__import__('marshal').loads" in stage1_src or "marshal.loads" in stage1_src:
        # Round 11: raw bytes are a marshal-encoded code object
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from decompiler import decompile_module
        import ast as _ast
        co = marshal.loads(raw)
        mod = decompile_module(co)
        return _ast.unparse(mod)
    else:
        return raw.decode("utf-8")


def _decode_ft_triple(key_int, K, hex_str):
    """Decode one (key, K, hex_str) triple from the round-10 _ft list."""
    enc = bytes.fromhex(hex_str)
    name = bytes((b ^ ((K + i * 11 + 5) & 0xFF)) for i, b in enumerate(enc)).decode()
    return key_int, name


def _expand_list_elts(list_node):
    """Expand list elements, handling [*iterable] spread patterns.

    In round 11, the list is built as [*(tuples)] which produces:
        List(elts=[Starred(value=Tuple(elts=[...]), ctx=Load())])

    Returns the flat list of element nodes (the tuples themselves).
    """
    elts = list_node.elts
    if len(elts) == 1 and isinstance(elts[0], ast.Starred):
        inner = elts[0].value
        if isinstance(inner, ast.Tuple):
            return inner.elts
    return elts


def _parse_ft_loop(tree):
    """Extract _ft entries from the round-10 loop-based construction.

    Looks for:
        LIST_VAR = [(key, K, hex_str), ...]
        DICT_VAR = {}
        for _fk, _fK, _fv in LIST_VAR:
            DICT_VAR[_fk] = getattr(__import__('builtins'), ...)

    Returns (ft_varname, ft_dict) or (None, {}) if pattern not found.
    """
    # Collect all Name -> list-of-tuples assignments
    list_var_values = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            t = stmt.targets[0]
            if isinstance(t, ast.Name) and isinstance(stmt.value, ast.List):
                list_var_values[t.id] = stmt.value

    ft_varname = None
    ft_dict = {}

    for stmt in tree.body:
        if not isinstance(stmt, ast.For):
            continue
        # Check: for _fk, _fK, _fv in LIST_VAR
        if not (isinstance(stmt.iter, ast.Name) and stmt.iter.id in list_var_values):
            continue
        if not (isinstance(stmt.target, ast.Tuple) and len(stmt.target.elts) == 3):
            continue
        list_val = list_var_values[stmt.iter.id]
        # Check body has a subscript assignment with getattr
        body = stmt.body
        if len(body) != 1:
            continue
        assign = body[0]
        if not isinstance(assign, ast.Assign):
            continue
        if len(assign.targets) != 1:
            continue
        tgt = assign.targets[0]
        if not (isinstance(tgt, ast.Subscript) and isinstance(tgt.value, ast.Name)):
            continue
        ft_varname = tgt.value.id
        # Parse the list of triples; handle [*(...)] spread from round 11
        for elt in _expand_list_elts(list_val):
            if not (isinstance(elt, ast.Tuple) and len(elt.elts) == 3):
                continue
            try:
                key_int = ast.literal_eval(elt.elts[0])
                K_val = ast.literal_eval(elt.elts[1])
                hex_str = ast.literal_eval(elt.elts[2])
                _, name = _decode_ft_triple(key_int, K_val, hex_str)
                ft_dict[key_int] = name
            except Exception:
                continue
        break

    return ft_varname, ft_dict


def _parse_c_loop(tree):
    """Extract _c entries from the round-10 masked loop construction.

    Looks for:
        _cm = <int>
        LIST_VAR = [(ckey, masked_val), ...]
        DICT_VAR = {}
        for _ck, _cv in LIST_VAR:
            DICT_VAR[_ck] = _cv ^ _cm

    Returns (cv_varname, c_dict) or (None, {}) if pattern not found.
    """
    # Collect _cm value
    cm = None
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            t = stmt.targets[0]
            if isinstance(t, ast.Name) and t.id == "_cm":
                try:
                    cm = ast.literal_eval(stmt.value)
                except Exception:
                    pass

    if cm is None:
        return None, {}

    # Collect list-of-pairs variables
    list_var_values = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            t = stmt.targets[0]
            if isinstance(t, ast.Name) and isinstance(stmt.value, ast.List):
                list_var_values[t.id] = stmt.value

    cv_varname = None
    c_dict = {}

    for stmt in tree.body:
        if not isinstance(stmt, ast.For):
            continue
        if not (isinstance(stmt.iter, ast.Name) and stmt.iter.id in list_var_values):
            continue
        if not (isinstance(stmt.target, ast.Tuple) and len(stmt.target.elts) == 2):
            continue
        list_val = list_var_values[stmt.iter.id]
        body = stmt.body
        if len(body) != 1:
            continue
        assign = body[0]
        if not isinstance(assign, ast.Assign):
            continue
        if len(assign.targets) != 1:
            continue
        tgt = assign.targets[0]
        if not (isinstance(tgt, ast.Subscript) and isinstance(tgt.value, ast.Name)):
            continue
        cv_varname = tgt.value.id
        # Handle [*(...)] spread from round 11
        for elt in _expand_list_elts(list_val):
            if not (isinstance(elt, ast.Tuple) and len(elt.elts) == 2):
                continue
            try:
                ckey = ast.literal_eval(elt.elts[0])
                masked = ast.literal_eval(elt.elts[1])
                c_dict[ckey] = masked ^ cm
            except Exception:
                continue
        break

    return cv_varname, c_dict


def stage2_decode(stage2_src):
    tree = ast.parse(stage2_src)

    D2 = None
    K2 = None
    ft_varname = None
    cv_varname = None
    ft_dict = {}
    c_dict = {}

    # Collect _D2 and _K2
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            t = stmt.targets[0]
            if isinstance(t, ast.Name):
                if t.id == "_D2":
                    D2 = parse_literal(stmt.value)
                elif t.id == "_K2":
                    K2 = parse_literal(stmt.value)

    # Try round-10 loop-based _ft construction first
    ft_varname, ft_dict = _parse_ft_loop(tree)

    # Try round-10 masked _c construction
    cv_varname, c_dict = _parse_c_loop(tree)

    # Fall back to round-8/9 subscript-assignment style if loops not found
    if not ft_dict or not c_dict:
        for stmt in tree.body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                t = stmt.targets[0]
                if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name):
                    name = t.value.id
                    key_int = parse_literal(t.slice)
                    if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, int):
                        if not c_dict:
                            c_dict[key_int] = stmt.value.value
                            cv_varname = name
                        elif cv_varname == name:
                            c_dict[key_int] = stmt.value.value
                    else:
                        try:
                            builtin_name = decode_ft_value(stmt.value)
                            if not ft_dict:
                                ft_varname = name
                            if ft_varname == name:
                                ft_dict[key_int] = builtin_name
                        except Exception:
                            pass

    # Stage 2 uses position-dependent XOR (round 10)
    raw = lzma.decompress(decrypt_xor16_pos(D2, K2))
    # Use ctypes-style marshal load matching what the obfuscator uses
    import ctypes
    api = ctypes.pythonapi
    api.PyMarshal_ReadObjectFromString.restype = ctypes.py_object
    api.PyMarshal_ReadObjectFromString.argtypes = [ctypes.c_char_p, ctypes.c_ssize_t]
    code_obj = api.PyMarshal_ReadObjectFromString(raw, len(raw))
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
