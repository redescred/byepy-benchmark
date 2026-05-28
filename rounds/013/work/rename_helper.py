"""Apply readable name mappings to recovered files."""
import ast
import sys
from pathlib import Path
from cleanup import IdentifierRenamer

def rename_file(src_path, dst_path, func_names, var_names=None):
    """Apply name mappings to a recovered Python file.
    
    func_names: list of (old_name, new_name) pairs for functions
    var_names: list of (old_name, new_name) pairs for variables
    """
    src = Path(src_path).read_text()
    tree = ast.parse(src)
    mapping = {}
    for old, new in (func_names or []):
        mapping[old] = new
    for old, new in (var_names or []):
        mapping[old] = new
    tree = IdentifierRenamer(mapping).visit(tree)
    ast.fix_missing_locations(tree)
    result = ast.unparse(tree)
    Path(dst_path).write_text(result + '\n', encoding='utf-8')
    print(f"Written {dst_path}")

