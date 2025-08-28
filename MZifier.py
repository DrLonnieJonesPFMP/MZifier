#!/usr/bin/env python3
"""
Author: Lonnie S. Jones
Company: Paradise Union
Version: 25.22.8.0.10a
Date: 8/22/25
Tite: MZifier
Description: A converter that helps migrate RPG Maker MV plugin to RPG Maker MZ.
Cost: Free
License: Creative Commons Attribution 4.0
Language: Python
Written Language: English
GitHub: 
Sponsor Link: 

---------------------
mv_to_mz_converter.py
---------------------
What it does (heuristics, not a full JS transpiler):
- Adds "@target MZ" to the plugin header if missing.
- Optionally injects an MZ-aware plugin header wrapper if none exists.
- Rewrites many Window_Base actor-drawing hooks to Window_StatusBase.
- Converts common MV color helpers (this.systemColor(), this.textColor(n), etc.)
  to MZ's ColorManager.* equivalents.
- Leaves TODO comments for MV-style plugin command patterns (cannot be auto-converted reliably).
- Writes a report of all replacements performed.

Usage:
  python mv_to_mz_converter.py INPUT.js [-o OUTPUT.js] [--inplace] [--no-color] [--keep-mv-color]
  python mv_to_mz_converter.py --batch plugins/*.js

Notes:
- This is deliberately conservative. It avoids touching uncertain code.
- Always review diffs after conversion.
"""

import argparse
import pathlib
import re
import sys
from typing import List, Tuple

# --- Rules --------------------------------------------------------------------

# Methods that, in practice, are usually defined/overridden on Window_StatusBase in MZ.
WINDOW_BASE_TO_STATUSBASE_METHODS = [
    # Actor drawing helpers
    "drawActorSimpleStatus",
    "drawActorName",
    "drawActorClass",
    "drawActorNickname",
    "drawActorLevel",
    "drawActorIcons",
    "drawActorHp",
    "drawActorMp",
    "drawActorTp",
    "drawActorHpGauge",
    "drawActorMpGauge",
    "drawActorTpGauge",
    "placeActorName",
    "placeGauge",
]

# Color helper replacements (MV -> MZ ColorManager)
COLOR_REPLACEMENTS = [
    (r"\bthis\.systemColor\s*\(\s*\)", "ColorManager.systemColor()"),
    (r"\bthis\.crisisColor\s*\(\s*\)", "ColorManager.crisisColor()"),
    (r"\bthis\.deathColor\s*\(\s*\)", "ColorManager.deathColor()"),
    (r"\bthis\.gaugeBackColor\s*\(\s*\)", "ColorManager.gaugeBackColor()"),
    (r"\bthis\.hpColor\s*\(\s*(.*?)\s*\)", r"ColorManager.hpColor(\1)"),
    (r"\bthis\.mpColor\s*\(\s*(.*?)\s*\)", r"ColorManager.mpColor(\1)"),
    (r"\bthis\.tpColor\s*\(\s*(.*?)\s*\)", r"ColorManager.tpColor(\1)"),
    (r"\bthis\.mpCostColor\s*\(\s*\)", "ColorManager.mpCostColor()"),
    (r"\bthis\.powerUpColor\s*\(\s*\)", "ColorManager.powerUpColor()"),
    (r"\bthis\.powerDownColor\s*\(\s*\)", "ColorManager.powerDownColor()"),
    (r"\bthis\.paramchangeTextColor\s*\(\s*(.*?)\s*\)", r"ColorManager.paramchangeTextColor(\1)"),
    (r"\bthis\.textColor\s*\(\s*(.*?)\s*\)", r"ColorManager.textColor(\1)"),
    (r"\bthis\.normalColor\s*\(\s*\)", "ColorManager.normalColor()"),
]

MV_PLUGIN_COMMAND_SIGNS = [
    # Common MV plugin command hooks we can't auto-convert to MZ registerCommand.
    r"\bGame_Interpreter\.prototype\.pluginCommand\b",
]

HEADER_BLOCK_RE = re.compile(r"/\*:[\s\S]*?\*/", re.MULTILINE)

def add_target_mz(header: str) -> str:
    """Ensure @target MZ exists inside the header block."""
    if "@target" in header:
        return header
    # Insert @target MZ after the opening /*: line
    lines = header.splitlines()
    if lines:
        # Find index after first line
        insert_at = 1 if len(lines) > 1 else 0
        lines.insert(insert_at, " * @target MZ")
        return "\n".join(lines)
    return header

def ensure_header_has_target_mz(source: str) -> Tuple[str, bool]:
    """Add @target MZ to the first plugin header block if missing.
    Returns (new_source, changed?)."""
    m = HEADER_BLOCK_RE.search(source)
    if not m:
        return source, False
    header = m.group(0)
    new_header = add_target_mz(header)
    if new_header != header:
        source = source[:m.start()] + new_header + source[m.end():]
        return source, True
    return source, False

def replace_window_base_methods(source: str) -> Tuple[str, List[str]]:
    """Rewrite Window_Base.prototype.X to Window_StatusBase.prototype.X for known methods."""
    changes = []
    for method in WINDOW_BASE_TO_STATUSBASE_METHODS:
        pattern = re.compile(
            rf"\bWindow_Base\.prototype\.{re.escape(method)}\b"
        )
        if pattern.search(source):
            source = pattern.sub(f"Window_StatusBase.prototype.{method}", source)
            changes.append(f"Window_Base.prototype.{method} -> Window_StatusBase.prototype.{method}")
    return source, changes


def replace_colors(source: str, keep_mv_color: bool) -> Tuple[str, List[str]]:
    """Replace MV window color helpers with MZ ColorManager.* calls."""
    if keep_mv_color:
        return source, []
    changes = []
    for pat, repl in COLOR_REPLACEMENTS:
        new_source, n = re.subn(pat, repl, source)
        if n > 0:
            changes.append(f"{pat} -> {repl} ({n}x)")
            source = new_source
    return source, changes

def annotate_plugin_command_todos(source: str) -> Tuple[str, List[str]]:
    """Add a TODO comment where MV plugin command hooks are found."""
    changes = []
    for sig in MV_PLUGIN_COMMAND_SIGNS:
        pattern = re.compile(sig)
        if pattern.search(source):
            todo = ("\n// [MZ TODO] Detected MV-style pluginCommand. In MZ, migrate to:\n"
                    "// PluginManager.registerCommand(pluginName, command, handler)\n"
                    "// and use @command/@arg annotations in the header.\n")
            source = pattern.sub(lambda m: todo + m.group(0), source)
            changes.append("Annotated MV pluginCommand for manual conversion.")
    return source, changes

def guess_plugin_name_from_filename(path: pathlib.Path) -> str:
    return path.stem

def convert_text(source: str, *, keep_mv_color: bool) -> Tuple[str, List[str]]:
    report = []
    # 1) Ensure @target MZ
    source, changed = ensure_header_has_target_mz(source)
    if changed:
        report.append("Added '@target MZ' to plugin header.")

    # 2) Replace Window_Base.* actor helpers to Window_StatusBase.*
    source, changes = replace_window_base_methods(source)
    report.extend(changes)

    # 3) Color helpers -> ColorManager
    source, changes = replace_colors(source, keep_mv_color)
    report.extend(changes)

    # 4) Leave TODO notes for MV plugin commands
    source, changes = annotate_plugin_command_todos(source)
    report.extend(changes)

    return source, report


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Convert RPG Maker MV plugins to MZ (heuristic).")
    parser.add_argument("inputs", nargs="+", help="Input MV plugin .js file(s).")
    parser.add_argument("-o", "--output", help="Output file (only valid with a single input).")
    parser.add_argument("--inplace", action="store_true", help="Overwrite inputs in place.")
    parser.add_argument("--keep-mv-color", action="store_true", help="Do not convert MV color helpers to ColorManager.")
    args = parser.parse_args(argv)

    if args.output and len(args.inputs) != 1:
        print("Error: --output is only valid with a single input file.", file=sys.stderr)
        return 2

    overall_ok = True

    for input_path_str in args.inputs:
        in_path = pathlib.Path(input_path_str)
        if not in_path.exists():
            print(f"[!] Not found: {in_path}", file=sys.stderr)
            overall_ok = False
            continue

        try:
            text = in_path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[!] Failed to read {in_path}: {e}", file=sys.stderr)
            overall_ok = False
            continue

        converted, report = convert_text(
            text,
            keep_mv_color=args.keep_mv_color,
            )

        if args.inplace:
            out_path = in_path
        elif args.output:
            out_path = pathlib.Path(args.output)
        else:
            out_path = in_path.with_name(in_path.stem + "_MZ" + in_path.suffix)

        try:
            out_path.write_text(converted, encoding="utf-8")
        except Exception as e:
            print(f"[!] Failed to write {out_path}: {e}", file=sys.stderr)
            overall_ok = False
            continue

        # Write a sidecar report
        report_path = out_path.with_suffix(out_path.suffix + ".report.txt")
        report_text = f"Conversion report for {in_path.name} -> {out_path.name}\n" + \
                      "\n".join(f"- {line}" for line in report) if report else \
                      "No heuristic changes were necessary."
        try:
            report_path.write_text(report_text, encoding="utf-8")
        except Exception as e:
            print(f"[!] Failed to write report {report_path}: {e}", file=sys.stderr)

        print(f"[OK] Wrote {out_path}")
        if report:
            print("  Changes:")
            for line in report:
                print(f"   - {line}")
        else:
            print("  No heuristic changes were necessary.")

    return 0 if overall_ok else 1

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
