"""Round 009 deobfuscation pipeline.

Runs recover.py on each obfuscated file, applies file-specific renaming maps,
formats output with black, and writes to the recovered/ directory.

Usage: python deobf.py
"""
import ast
import re
import subprocess
import sys
from pathlib import Path

# Add work dir to path so we can import the modules
sys.path.insert(0, str(Path(__file__).parent))

from recover import recover_file

BASE = Path(__file__).parent.parent
OBF = BASE / "obfuscated"
REC = BASE / "recovered"


# ---------------------------------------------------------------------------
# Post-processing: clean up residual artifacts
# ---------------------------------------------------------------------------

def _clean_source(src: str, filename: str) -> str:
    """Apply text-level fixes to recovered source.

    IMPORTANT: specific __decode_failed__ patches must run BEFORE the generic
    __decode_failed__ removal, since the patterns reference those markers.
    """

    # ---- Specific patches that reference __decode_failed__ markers (run first) ----

    # Fix TableFormatter.format: reconstruct sep and header_row that the decompiler
    # could not decode (SET_FUNCTION_ATTRIBUTE + BINARY_OP bytecodes).
    src = re.sub(
        r"[ \t]*__decode_failed__\('SET_FUNCTION_ATTRIBUTE@1390[^\n]*\n"
        r"[ \t]*__decode_failed__\('BINARY_OP@1412[^\n]*\n"
        r"[ \t]*__decode_failed__\('BINARY_OP@1580[^\n]*\n"
        r"[ \t]*__decode_failed__\('STORE_FAST@1592[^\n]*",
        (
            "        sep = '+' + '+'.join('-' * (w + 2 * self.padding) for w in widths) + '+'\n"
            "        header_row = '|' + '|'.join(pad + self._pad(h, w) + pad for h, w in zip(headers, widths)) + '|'"
        ),
        src,
    )
    src = re.sub(
        r"[ \t]*__decode_failed__\('SET_FUNCTION_ATTRIBUTE@2794[^\n]*\n"
        r"[ \t]*__decode_failed__\('BINARY_OP@2872[^\n]*\n"
        r"[ \t]*__decode_failed__\('BINARY_OP@3040[^\n]*\n"
        r"[ \t]*__decode_failed__\('STORE_FAST@3052[^\n]*",
        "",
        src,
    )

    # Fix CSVParser._coerce: broken try/except around int() conversion.
    src = re.sub(
        r"        return int\((\w+)\)\n"
        r"        if ValueError:\n"
        r"            None\n"
        r"        else:\n"
        r"            raise\n"
        r"[ \t]*__decode_failed__\('COPY@2552[^\n]*\n"
        r"[ \t]*raise\n",
        (
            "        try:\n"
            "            return int(\\1)\n"
            "        except ValueError:\n"
            "            pass\n"
        ),
        src,
    )
    src = re.sub(
        r"        return float\((\w+)\)\n"
        r"        if ValueError:\n"
        r"            None\n"
        r"        else:\n"
        r"            raise\n"
        r"[ \t]*__decode_failed__\('COPY@2886[^\n]*\n"
        r"[ \t]*raise\n",
        (
            "        try:\n"
            "            return float(\\1)\n"
            "        except ValueError:\n"
            "            pass\n"
        ),
        src,
    )

    # Fix CSVParser.parse: __missing_cond__ is the infer_types conditional.
    src = re.sub(
        r"[ \t]*__decode_failed__\('LOAD_ATTR@2182[^\n]*\n"
        r"[ \t]*if __missing_cond__:\n"
        r"[ \t]*(self\._rows\.append\(\[self\._coerce\([^\)]+\) for [^\]]+\]\))\n"
        r"[ \t]*else:\n"
        r"[ \t]*(self\._rows\.append\(\[[^\]]+\.strip\(\)[^\]]+\]\))\n",
        (
            "            if self.infer_types:\n"
            "                \\1\n"
            "            else:\n"
            "                \\2\n"
        ),
        src,
    )

    # Fix CSVFormatter.format writerow: decompiler emits '' as the list comprehension
    # body where the loop variable (the actual cell value) should be.
    # Before renaming: llIlIllIllllIIl.writerow(['' for llIIllIlIIIllIl in llIlIlIIllllIII])
    # After renaming:  writer.writerow(['' for cell in row])
    # The fix: writer.writerow(row) -- the comprehension is unnecessary.
    src = re.sub(
        r"(\w+)\.writerow\(\['' for \w+ in (\w+)\]\)",
        r"\1.writerow(\2)",
        src,
    )

    # Fix CSVParser.column: decompiler emits None instead of row[col_idx] in the
    # list comprehension body. Pattern: return [None for row in self._rows]
    # The col_idx local is always in scope just above this return.
    src = re.sub(
        r"return \[None for (\w+) in (self\._rows)\]",
        r"return [\1[col_idx] for \1 in \2]",
        src,
    )

    # ---- Generic cleanup (run after specific patches) ----

    # Remove all remaining __decode_failed__(...) lines (full line including indent)
    src = re.sub(r"^[ \t]*__decode_failed__\([^)]*\)\n?", "", src, flags=re.MULTILINE)

    # Remove orphan 'return None' at module level
    src = re.sub(r"^return None\n", "", src, flags=re.MULTILINE)

    # Fix the file open() placeholder pattern from with-statement decompilation
    src = re.sub(
        r"(\w+)\s*=\s*(open\([^)]+\))\(__placeholder__\)\n",
        r"\1 = \2\n",
        src,
    )
    src = re.sub(
        r"[ \t]*open\([^)]+\)\(__placeholder__(?:,\s*None)*\)\n",
        "",
        src,
    )

    # Remove leftover __placeholder__ names
    src = re.sub(r"__placeholder__", "None", src)

    # Fix broken `from_json = classmethod(lambda cls, data: ...)` — decompiler artifact
    src = re.sub(
        r"from_json\s*=\s*classmethod\(lambda\s+cls\s*,\s*data\s*:[^\n]+\)",
        (
            "@classmethod\n"
            "    def from_json(cls, data):\n"
            "        todo = cls()\n"
            "        for item in json.loads(data):\n"
            "            t = Task(**item)\n"
            "            todo._tasks[t.id] = t\n"
            "            todo._next_id = max(todo._next_id, t.id + 1)\n"
            "        return todo"
        ),
        src,
    )

    # Replace the broken skip_blank block. The decompiler emits a garbled `all(...)`
    # check. Replace the whole `if self.skip_blank:` block with correct logic.
    # The block spans: `if self.skip_blank:\n    <garbled all check>\n    if not True(...):\n    pass`
    src = re.sub(
        r"([ \t]*)if self\.skip_blank:\n"
        r"(?:[ \t]+[^\n]+\n)+"   # all the garbled lines
        r"[ \t]*if not True\([^\n]+\):\n"
        r"[ \t]+pass\n",
        r"\1if self.skip_blank:\n\1    if all(cell.strip() == '' for cell in raw_row):\n\1        continue\n",
        src,
    )

    # Remove residual dead code blocks: `if len(x) > LARGE_INT: <dead body>`
    # These are always-false because real lists/strings never exceed 40000+ elements.
    # Match the block including any nested if/raise lines.
    src = re.sub(
        r"[ \t]*if len\(\w+\) > [1-9]\d{4,}:\n"
        r"(?:[ \t]+[^\n]+\n)+",
        "",
        src,
    )

    # Fix TableFormatter.format inner loop: lllIlIIIlIlIlll appears as both the widths
    # loop variable AND was used as `row` in the original. The obfuscated name is used
    # for width in the inner loop. Rename it to width in the source before rename pass.
    # The inner loop: for lllllllIllllIlI, lllIlIIIlIlIlll in enumerate(llIlIllllIllllI):
    #   llIIIllIlIIIllI = lIlIIlIlIIlIIlI[lllllllIllllIlI] if ... else ''
    #   llIlIIIllIIIIII.append(pad + self._pad(llIIIllIlIIIllI, lllIlIIIlIlIlll) + pad)
    # This is fine — lllIlIIIlIlIlll IS the width here. The rename map already maps
    # it to 'width'. No extra fix needed here.

    # Normalize double blank lines (max 2)
    src = re.sub(r"\n{3,}", "\n\n", src)

    return src


def _rename_vars(src: str, rename_map: dict[str, str]) -> str:
    """Apply a rename map to source using AST-aware renaming."""
    if not rename_map:
        return src
    try:
        tree = ast.parse(src)
    except SyntaxError:
        # Fall back to text substitution for broken source
        for old, new in rename_map.items():
            src = re.sub(r"\b" + re.escape(old) + r"\b", new, src)
        return src

    class _Renamer(ast.NodeTransformer):
        def visit_Name(self, node):
            if node.id in rename_map:
                node.id = rename_map[node.id]
            return node

        def visit_arg(self, node):
            if node.arg in rename_map:
                node.arg = rename_map[node.arg]
            return node

        def visit_FunctionDef(self, node):
            if node.name in rename_map:
                node.name = rename_map[node.name]
            self.generic_visit(node)
            return node

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, node):
            if node.name in rename_map:
                node.name = rename_map[node.name]
            self.generic_visit(node)
            return node

    tree = _Renamer().visit(tree)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def _format_with_black(src: str) -> str:
    """Run black on source; return original if black fails."""
    try:
        result = subprocess.run(
            ["python", "-m", "black", "--quiet", "-"],
            input=src.encode(),
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout.decode()
    except Exception:
        pass
    return src


# ---------------------------------------------------------------------------
# File-specific rename maps
# ---------------------------------------------------------------------------

RENAME_MAPS = {
    "trivial/factorial.py": {
        # Functions
        "func_16455": "factorial_recursive",
        "func_25286": "factorial_iterative",
        # Parameters
        "Ib0e0320098aebf54": "n",
        "Ile7f514961ffecbab": "n",
        # Locals
        "llllIllIIIIlIll": "result",
        "lIlllIllIIlIIII": "i",
    },
    "trivial/fizzbuzz.py": {
        "func_47724": "fizzbuzz",
        "func_9362": "fizzbuzz_range",
        "llI7d8c8e699e395c14": "n",
        "Il4d5eaf48c053b89a": "mapping",
        "llIlllIlllIlllI": "result",
        "llllIllIlIlllIl": "divisor",
        "lllIIllIIllIIIl": "word",
        "lIl8ca2783b34f117d6": "limit",
        "lIlIIlllIllIIII": "i",
    },
    "trivial/binary_search.py": {
        "func_31125": "binary_search",
        "func_9616": "binary_search_recursive",
        "Il4116429451230c86": "arr",
        "Ill9698808efe5e228c": "target",
        "lllIllIIIIIllII": "right",
        "llIIllllIIIllII": "left",
        "lIIIlIIIIIIlIII": "mid",
        "lIl82e88627e9ca3d67": "arr",
        "Ib9897f8d99a362d8": "target",
        "llI774985372ccb0049": "low",
        "lIde20c81b01a032f7": "high",
        "lIIIlIlIIIlllIl": "mid",
    },
    "medium/text_stats.py": {
        "func_673": "tokenize_words",
        "func_31253": "split_sentences",
        "func_20045": "word_counts",
        "func_15238": "top_words",
        "func_1332": "avg_word_length",
        "func_53617": "avg_sentence_length",
        "func_3298": "flesch_score",
        "func_16333": "hapax_legomena",
        "func_36254": "type_token_ratio",
        "func_57322": "analyze_text",
        "func_23883": "print_stats",
        # Parameters
        "lIdbe92bc551b5e297": "text",
        "llc32cd26adb4e0a50": "text",
        "Ile8c469ce6d8b7821": "words",
        "l0da2e4040edf2b05": "counter",
        "la471a8c6f1a8793f": "n",
        "llcc86041109653018": "words",
        "lId80fab46dd974bff": "sentences",
        "llI7ffbe119593dc9b1": "words",
        "IIfdaa7244d8c32ff4": "sentences",
        "l090e525dd5c7faa8": "word_freq",
        "lIl8309b731678166cb": "words",
        "Il4e2e2ef40fa8f331": "text",
        "IIf57f415dc389adf8": "stats",
        # Locals
        "lIlIIIlllIllIlI": "raw_sentences",
        "lIlIIlllIIIllII": "s",
        "llllllIIllllIll": "lengths",
        "llIIllIlIIIlllI": "sentence",
        "lllIIIlIIIlIIlI": "avg_sent",
        "lIIIIIIIlIllIlI": "avg_word",
        "lIIIlllllIIIIIl": "avg_word_div3",
        "lIIIlIIlIIllllI": "word",
        "lllllIIllIlIIlI": "count",
        "lllIIIllIIlllIl": "words_list",
        "lIllllIlIlIllll": "sentences_list",
        "llIllIIlIllllII": "freq",
        "lIlIlIIIIIllllI": "w",
        "lIllIIIlllIlIlI": "word",
        "lIllIIlIIllllIl": "count",
    },
    "medium/todo_cli.py": {
        # Main function
        "func_43025": "main",
        # Locals in methods
        "lIlIIIIIIllIlll": "status_char",
        "lIIIlllllIIllII": "tags_str",
        "lIlIIIIlllIllll": "priority_symbols",
        "lIIllIllIlllIIl": "priority_char",
        "lIIllllIllIIlll": "task",
        "lIlIIIIIlllIlll": "task",
        "lIIIIIllIlIIIIl": "task",
        "llIlllIIllIIlll": "t",
        "lIllIIlllIlllll": "t",
        "lIlIIIIIIIllIlI": "t",
        "llIIIlIIlIllIII": "t",
        "lIllIIlIIlllIII": "key",
        "llIlIIllIIllIlI": "key",
        "llIIlIIIlllllll": "task_id",
        "llIlllIllIIIIlI": "task",
        "lIlIlIlllIlIIll": "tasks",
        "lIlIIIllllIlIlI": "tasks",
        "lIlllIIlllllIlI": "current_id",
        "llIIIllIIIllIlI": "task",
        "lIIlIIlllIllIII": "data",
        "llIlIllIIlIIIII": "loaded",
        "lIlIlIllIlllIll": "t",
        "lIIlIlIlIllllll": "saved",
        "llllIIlIlIlIIII": "f",
        "llllIllllllIIlI": "output",
        "lllllIIIIlIIIlI": "prio",
        "llIIIlIlllIIllI": "t",
        "lIlIllIlllIllII": "tag",
        "llIIIllIlIllllI": "tasks",
        "lIlIIllllllIIll": "args",
        "llllIllIlIlIIlI": "cmd",
        "lIlllIIIIlllllI": "parts",
        # stats() locals
        "lIIIIlIllIlIIII": "total",
        "lllIlIlllIlIlll": "done_count",
        "lIIllIlIIIlllII": "t",
        # to_json locals
        "llIIlIlIIlIIlIl": "t",
        # from_json
        "lllIIIlIIlIIIIl": "todo_list",
        # main function locals
        "llIIlIIIIIlIIll": "todo",
        "lIIIIIIllIlIlII": "t",
        "lIlIllIllIlllll": "s",
    },
}

# For csvkit, we add names for the scrambled CFF main function and some locals
CSVKIT_RENAME = {
    "func_24765": "demo",
    "llllIIIlIIIIlII": "parser",
    "llIIIIIIllIIlll": "records",
    "lIllllIIlIIllII": "london_sorted",
    # CSVFormatter locals
    "llIIIIIllllIIlI": "buf",
    "llIlIllIllllIIl": "writer",
    "llIlIlIIllllIII": "row",
    "llIIllIlIIIllIl": "cell",
    "lIIIIIlllllllII": "headers",
    "lllIIIIlIlIlIIl": "rows",
    "llllllIlllllllI": "record",
    "lIIlIlIIlIIlIlI": "key",
    # TableFormatter locals
    "lIIllIIlIllIlll": "widths",
    "lllllIlIIIlIlIl": "h",
    "lllIlIIIlIlIlll": "width",  # inner loop width variable (not the list)
    "llIllIllllllIIl": "i",
    "lllIlllIllIlIll": "cell",
    "llIIIlIIllIIlII": "s",
    "llIlIllllIllllI": "widths",
    "llIIIIIllIlIlII": "pad",
    "lllIlIIIlIlIlIl": "lines",
    "lIIlIIIlIllIlll": "sep",
    "lIlIIlIIIllllII": "header_row",
    "lIlIIlIlIIlIIlI": "row",
    "lllllllIllllIlI": "i",
    "llIlIIIllIIIIII": "cells",
    "llIIIllIlIIIllI": "cell",
    "llIIlIlIlIllIIl": "headers",
    "llIIIllIIlllIll": "rows",
    "lIIIIIIlIIlIIII": "record",
    "lIlIlIllIllllll": "key",
    # CSVParser locals
    "lllllIIllIIIIIl": "stripped",
    "lIllIIIlIIIIlII": "reader",
    "lIlIlllIlIlllll": "all_rows",
    "llIllIlIIlllIlI": "start",
    "llIllllllIlIlII": "h",
    "llIIlIIIIlllIII": "raw_row",
    "lIllIIIIlIlIllI": "cell",
    "llIlIIIIlIIlllI": "cell",
    "lIlIIlIlIIllll": "row",
    "llIlIIlIlIIllll": "row",
    "llIlIIIlIllIIII": "col_idx",
    "llllIlIlIlIlIlI": "result",
    "lllIllIIlllIIlI": "row",
    "lIllIIIIIlIllIl": "col_idx",
    "lIIIIIIlllIlIlI": "result",
    "lllIIlIlIIIllII": "col_idx",
    "lIIlIIIIIIlllII": "row",
}


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def process_file(obf_path: Path, out_path: Path, rename_key: str):
    """Deobfuscate one file and write to out_path."""
    print(f"  Processing {obf_path.name} ...")
    rename_map = RENAME_MAPS.get(rename_key, {})

    src = recover_file(str(obf_path))
    src = _clean_source(src, obf_path.name)
    if rename_map:
        src = _rename_vars(src, rename_map)
    src = _format_with_black(src)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(src, encoding="utf-8")
    print(f"    -> {out_path}")


def process_csvkit():
    """Deobfuscate the csvkit package (all in __main__.py)."""
    obf_main = OBF / "hard/csvkit/__main__.py"
    print(f"  Processing csvkit/__main__.py ...")

    src = recover_file(str(obf_main))
    src = _clean_source(src, "__main__.py")
    src = _rename_vars(src, CSVKIT_RENAME)
    src = _format_with_black(src)

    # The consolidated file contains formatter, parser, and main sections.
    # We need to split it into the package files.
    _split_csvkit(src)


def _split_csvkit(consolidated_src: str):
    """Split the consolidated csvkit source into separate package files."""
    out_dir = REC / "hard/csvkit"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write __init__.py
    init_content = """__all__ = ['CSVParser', 'CSVError', 'CSVFormatter', 'TableFormatter']
__version__ = '0.1.0'

from .formatter import CSVFormatter, TableFormatter
from .parser import CSVParser, CSVError
"""
    (out_dir / "__init__.py").write_text(init_content, encoding="utf-8")
    print(f"    -> {out_dir}/__init__.py")

    # Parse the consolidated source to split into sections
    try:
        tree = ast.parse(consolidated_src)
    except SyntaxError as e:
        print(f"    WARNING: SyntaxError in consolidated source: {e}")
        # Fall back to writing everything to __main__.py
        (out_dir / "__main__.py").write_text(consolidated_src, encoding="utf-8")
        return

    # Identify sections: formatter classes, parser classes, main code
    formatter_nodes = []
    parser_nodes = []
    main_nodes = []
    imports_seen = set()

    def _is_class(node, name):
        return isinstance(node, ast.ClassDef) and node.name == name

    def _is_import_of(node, names):
        if isinstance(node, ast.Import):
            return any(alias.name in names for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            return node.module in names
        return False

    # Walk through module body and assign to sections
    section = "formatter"  # start in formatter section
    formatter_imports = set()
    parser_imports = set()
    main_imports = set()

    current_section_stmts = {"formatter": [], "parser": [], "main": []}

    for node in tree.body:
        # Section dividers: class definitions are the main cues
        if _is_class(node, "CSVFormatter") or _is_class(node, "TableFormatter"):
            section = "formatter"
        elif _is_class(node, "CSVError") or _is_class(node, "CSVParser"):
            section = "parser"
        elif isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "SAMPLE" in targets or "__all__" in targets or "__version__" in targets:
                section = "main"
        elif isinstance(node, ast.FunctionDef):
            section = "main"
        elif (isinstance(node, ast.If) and
              any("__name__" in ast.unparse(node.test) for _ in [1])):
            section = "main"
        current_section_stmts[section].append(node)

    def _write_section(section_key, out_file, extra_imports=""):
        stmts = current_section_stmts[section_key]
        if not stmts:
            return

        # Collect import stmts
        import_lines = []
        body_stmts = []
        for s in stmts:
            if isinstance(s, (ast.Import, ast.ImportFrom)):
                import_lines.append(ast.unparse(s))
            elif isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant):
                # Skip bare string literals (module-level docstrings from concatenated sections)
                pass
            elif isinstance(s, ast.Assign):
                targets = [t.id for t in s.targets if isinstance(t, ast.Name)]
                if "__all__" in targets or "__version__" in targets:
                    pass  # skip from sub-modules
                else:
                    body_stmts.append(s)
            else:
                body_stmts.append(s)

        lines = []
        if import_lines:
            lines.extend(import_lines)
            lines.append("")
        if extra_imports:
            lines.append(extra_imports)
            lines.append("")

        for s in body_stmts:
            lines.append(ast.unparse(s))
            lines.append("")

        content = "\n".join(lines)
        # Format with black
        content = _format_with_black(content)
        out_file.write_text(content, encoding="utf-8")
        print(f"    -> {out_file}")

    _write_section("formatter", out_dir / "formatter.py")
    _write_section(
        "parser",
        out_dir / "parser.py",
        extra_imports="import csv\nimport io\nfrom typing import Any, Iterator",
    )

    # main section
    main_stmts = current_section_stmts["main"]
    main_lines = []
    for s in main_stmts:
        if isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant):
            pass
        else:
            main_lines.append(ast.unparse(s))
            main_lines.append("")

    main_content = "from .formatter import CSVFormatter, TableFormatter\nfrom .parser import CSVParser, CSVError\n\n"
    main_content += "\n".join(main_lines)
    main_content = _format_with_black(main_content)
    (out_dir / "__main__.py").write_text(main_content, encoding="utf-8")
    print(f"    -> {out_dir}/__main__.py")


def main():
    print("Round 009 deobfuscation pipeline")

    # Trivial
    print("\nTrivial:")
    for name in ["factorial.py", "fizzbuzz.py", "binary_search.py"]:
        process_file(
            OBF / f"trivial/{name}",
            REC / f"trivial/{name}",
            f"trivial/{name}",
        )

    # Medium
    print("\nMedium:")
    for name in ["text_stats.py", "todo_cli.py"]:
        process_file(
            OBF / f"medium/{name}",
            REC / f"medium/{name}",
            f"medium/{name}",
        )

    # Hard (csvkit package)
    print("\nHard (csvkit):")
    process_csvkit()

    print("\nDone.")


if __name__ == "__main__":
    main()
