"""Full recovery pipeline for a single obfuscated file.

Usage: python recover.py <obfuscated.py> [<recovered_out.py>]

If <recovered_out.py> is omitted, prints to stdout.
"""
import ast
import sys
from pathlib import Path

from extract import extract_from_file
from decompiler import decompile_module
from cleanup import (
    TableSubstitutor,
    DeadCodeRemover,
    CFFUnflatten,
    ScrambledCFFUnflatten,
    XorStringDecoder,
    TrampolineCleanup,
    UserFuncCallRewrite,
    IdentifierRenamer,
    FrefCleanup,
)


def recover_file(obf_path, name_hint_map=None, user_func_overrides=None):
    """Recover source from an obfuscated file.

    name_hint_map: dict of {obfuscated_identifier -> desired_name}.
                   Used to give readable names to renamed identifiers.
    user_func_overrides: dict of {int_key -> readable_user_func_name}
    """
    info, _ = extract_from_file(obf_path)
    code = info["code"]
    ft_varname = info["ft_varname"]
    ft_table = info["ft"]
    cv_varname = info["cv_varname"]
    c_table = info["c"]

    # First pass: decompile bytecode to AST
    mod = decompile_module(code)

    # Substitute _ft[N] and _c[N]
    mod = TableSubstitutor(ft_varname, ft_table, cv_varname, c_table).visit(mod)
    ast.fix_missing_locations(mod)

    # Decode XOR strings
    mod = XorStringDecoder().visit(mod)
    ast.fix_missing_locations(mod)

    # Remove dead code
    mod = DeadCodeRemover().visit(mod)
    ast.fix_missing_locations(mod)

    # CFF reversal: try both the while-True pattern (round 8) and the scrambled
    # pattern (round 9 with while sv==X followed by separate if/elif blocks)
    mod = CFFUnflatten().visit(mod)
    ast.fix_missing_locations(mod)
    mod = ScrambledCFFUnflatten().visit(mod)
    ast.fix_missing_locations(mod)
    # Second pass in case dead code removal exposed more CFF structure
    mod = CFFUnflatten().visit(mod)
    ast.fix_missing_locations(mod)
    mod = ScrambledCFFUnflatten().visit(mod)
    ast.fix_missing_locations(mod)

    # Collapse trampoline (def TMP; _ft[k]=TMP; del TMP) into def
    user_key_to_name = dict(user_func_overrides or {})
    mod = TrampolineCleanup(ft_varname, user_key_to_name).visit(mod)
    ast.fix_missing_locations(mod)
    # Replace remaining _ft[KEY] in load context with the user function name
    mod = UserFuncCallRewrite(ft_varname, user_key_to_name).visit(mod)
    ast.fix_missing_locations(mod)

    # Apply identifier renames last
    if name_hint_map:
        mod = IdentifierRenamer(name_hint_map).visit(mod)
        ast.fix_missing_locations(mod)

    # Final safety net
    mod = FrefCleanup().visit(mod)
    ast.fix_missing_locations(mod)

    # Simplify boolean expressions
    from cleanup import BoolSimplifier, DataclassAnnFix
    mod = BoolSimplifier().visit(mod)
    mod = DataclassAnnFix().visit(mod)
    ast.fix_missing_locations(mod)

    # Replace any leftover non-AST sentinels with placeholder Name nodes so
    # ast.unparse doesn't blow up.
    mod = _PlaceholderSweeper().visit(mod)
    ast.fix_missing_locations(mod)

    # Drop trailing exception-handler trailers (naked raise, "if not None: raise")
    while mod.body and _is_orphan_trailer(mod.body[-1]):
        mod.body.pop()

    return ast.unparse(mod)


def _is_orphan_trailer(stmt):
    if isinstance(stmt, ast.Raise) and stmt.exc is None:
        return True
    if isinstance(stmt, ast.If):
        if (isinstance(stmt.test, ast.UnaryOp) and isinstance(stmt.test.op, ast.Not)
                and isinstance(stmt.test.operand, ast.Constant)
                and stmt.test.operand.value is None):
            return True
        if (isinstance(stmt.test, ast.Constant) and stmt.test.value is None):
            return True
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call) \
            and isinstance(stmt.value.func, ast.Name) \
            and stmt.value.func.id == "__decode_failed__":
        return True
    return False


class _PlaceholderSweeper(ast.NodeTransformer):
    def visit(self, node):
        # Pre-walk children; if we encounter a non-AST sentinel, replace it
        if not isinstance(node, ast.AST):
            return ast.Name(id="__placeholder__", ctx=ast.Load())
        for field in list(node._fields):
            val = getattr(node, field, None)
            if isinstance(val, list):
                new = []
                for item in val:
                    if isinstance(item, ast.AST):
                        new.append(self.visit(item))
                    elif item is None:
                        new.append(None)
                    else:
                        new.append(ast.Name(id="__placeholder__", ctx=ast.Load()))
                setattr(node, field, new)
            elif isinstance(val, ast.AST):
                setattr(node, field, self.visit(val))
            elif val is None:
                continue
            elif isinstance(val, (str, int, float, bytes, bool, tuple, type(...))):
                continue
            else:
                setattr(node, field, ast.Name(id="__placeholder__", ctx=ast.Load()))
        return node


if __name__ == "__main__":
    out = recover_file(sys.argv[1])
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(out, encoding="utf-8")
    else:
        print(out)
