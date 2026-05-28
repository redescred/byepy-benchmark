"""Extract stage-2 payload: marshalled code object + builtin lookup dict."""
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


def decode_inline(expr):
    """Decode the rhs of lookup assignments.

    These look like:
        bytes(_b^((C+_i*11+5)&255) for _i,_b in enumerate(bytes.fromhex('...'))).decode()
    """
    # call to .decode()
    if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute) and expr.func.attr == 'decode':
        bytes_call = expr.func.value
        # bytes(generator)
        gen = bytes_call.args[0]
        # generator: elt = _b ^ ((C + _i*11 + 5) & 255)
        elt = gen.elt
        # left side: Name _b ; right side: BinOp ... & 255
        # Pattern: BinOp(_b, BitXor, BinOp(BinOp(BinOp(Constant C, Add, BinOp(Name _i, Mult, Constant 11)), Add, Constant 5), BitAnd, Constant 255))
        # Easier: walk and find the constant C.
        # In the AST, _i ranges over enumerate(bytes.fromhex(...)).
        # We extract the hex argument and find the integer constants C and steps.
        for sub in ast.walk(gen):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr == 'fromhex':
                hex_str = sub.args[0].value
                data_bytes = bytes.fromhex(hex_str)
                break

        # Recover the XOR formula. We can do this generically by inspecting the
        # generator expression's elt: take all integer constants in order.
        # The formula is: _b ^ ((C + _i*M + A) & 255)
        # We only need the actual numeric values; just collect constants.
        consts = [n.value for n in ast.walk(elt) if isinstance(n, ast.Constant) and isinstance(n.value, int)]
        # consts order in this expression: C, 11, 5, 255 (after _b)
        # But the AST traversal may not be reliable; do it the simple way and just
        # try every permutation of three constants we see, using one as base.
        # The structure is fixed though: ast.dump shows the pattern.
        # We'll instead build via direct AST: BitXor(_b, BitAnd(Add(Add(Const C, Mult(_i, Const M)), Const A), Const 255))
        # Extract by recursion:
        def to_xor_func(node):
            # walk until BitAnd & 255
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitXor):
                right = node.right
                if isinstance(right, ast.BinOp) and isinstance(right.op, ast.BitAnd):
                    inner = right.left
                    # inner = ((C + _i*M) + A) or ((_i*M + C) + A) etc.
                    # Walk it, gather constants and substitutions for _i.
                    # We'll evaluate the inner expression for each _i symbolically.
                    return inner
            raise ValueError('unexpected formula structure')

        inner = to_xor_func(elt)

        # Substitute _i symbolically using a compile-and-call trick (no eval).
        # Build a function: lambda _i: (inner)
        wrapper = ast.parse('lambda _i: 0', mode='eval')
        wrapper.body.body = inner
        wrapper = ast.fix_missing_locations(wrapper)
        code_obj = compile(wrapper, '<x>', 'eval')
        formula = __import__('builtins').eval(code_obj, {})

        result = bytes(b ^ (formula(i) & 255) for i, b in enumerate(data_bytes))
        return result.decode()
    raise ValueError(f'unsupported expr: {ast.dump(expr)}')


def stage2(src: str):
    tree = ast.parse(src)
    data2 = None
    key2 = None
    lookup_name = None
    lookup_entries = {}

    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            if isinstance(tgt, ast.Name) and isinstance(node.value, ast.Constant):
                if tgt.id == '_D2':
                    data2 = node.value.value
                elif tgt.id == '_K2':
                    key2 = node.value.value
            if (isinstance(tgt, ast.Name) and isinstance(node.value, ast.Dict)
                    and node.value.keys == [] and node.value.values == []):
                lookup_name = tgt.id
            if (isinstance(tgt, ast.Subscript) and isinstance(tgt.value, ast.Name)
                    and lookup_name is not None and tgt.value.id == lookup_name):
                idx = ast.literal_eval(tgt.slice)
                # rhs is getattr(__import__('builtins'), <decoded-name-expr>)
                name_expr = node.value.args[1]
                decoded = decode_inline(name_expr)
                lookup_entries[idx] = decoded

    raw = lzma.decompress(bytes(b ^ key2[i % 16] for i, b in enumerate(data2)))
    code = marshal.loads(raw)
    return code, lookup_entries, lookup_name


if __name__ == '__main__':
    for p in sys.argv[1:]:
        path = Path(p)
        src1 = stage1(path)
        code, lookup, name = stage2(src1)
        print(f'=== {path} ===')
        print(f'globals lookup dict name: {name}')
        print(f'lookup entries: {lookup}')
        print()
        print('--- disassembly ---')
        dis.dis(code)
        print()
