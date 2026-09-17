#!/usr/bin/env python3
"""Pin minted Executa ids across every file that has to agree on them.

    python scripts/set-tool-id.py status
    python scripts/set-tool-id.py apply --tool tool-yourhandle-receipts-engine-ab12cd34
    python scripts/set-tool-id.py apply --skill skill-yourhandle-receipts-coach-ef56gh78
    python scripts/set-tool-id.py reset

**You usually do not need this.** `anna-app apps publish` mints the ids and
substitutes every ``bundled:<handle>`` reference itself, writing
``bundle/anna-tool-ids.js`` for the UI. Use this only to pin a specific id by
hand — for example to install the plugin on an Agent outside the app flow.

Three files must carry the same tool id, because the harness spawns the plugin
with ``uv run --project . <tool_id>`` and the Agent matches the running plugin
to the catalogue by exact string equality:

1. ``executas/receipts-engine/executa.json`` → ``tool_id``
2. ``executas/receipts-engine/pyproject.toml`` → ``[project].name`` and the
   ``[project.scripts]`` key
3. ``ui/src/lib/ids.ts`` → the dev fallback constant

``status`` reports whether they agree; it exits non-zero when they do not, so
it can gate a commit.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIR = REPO_ROOT / "executas" / "receipts-engine"
SKILL_DIR = REPO_ROOT / "executas" / "receipts-coach"

EXECUTA_JSON = ENGINE_DIR / "executa.json"
PYPROJECT = ENGINE_DIR / "pyproject.toml"
IDS_TS = REPO_ROOT / "ui" / "src" / "lib" / "ids.ts"
SKILL_MD = SKILL_DIR / "SKILL.md"
SKILL_JSON = SKILL_DIR / "executa.json"

DEV_TOOL_ID = "tool-dev-receipts-engine"
DEV_SKILL_ID = "skill-dev-receipts-coach"

TOOL_ID_RE = re.compile(r"^(tool|skill)-[A-Za-z0-9_.\-]+$")


def read_tool_ids() -> dict[str, str]:
    """Current tool id as each file states it."""
    found: dict[str, str] = {}

    if EXECUTA_JSON.is_file():
        found["executa.json"] = json.loads(EXECUTA_JSON.read_text(encoding="utf-8")).get(
            "tool_id", ""
        )

    if PYPROJECT.is_file():
        text = PYPROJECT.read_text(encoding="utf-8")
        name = re.search(r'^name\s*=\s*"([^"]+)"', text, re.MULTILINE)
        script = re.search(r'^"([^"]+)"\s*=\s*"receipts_engine\.plugin:main"', text, re.MULTILINE)
        found["pyproject.name"] = name.group(1) if name else ""
        found["pyproject.scripts"] = script.group(1) if script else ""

    if IDS_TS.is_file():
        match = re.search(r'DEV_TOOL_ID\s*=\s*"([^"]+)"', IDS_TS.read_text(encoding="utf-8"))
        found["ui/src/lib/ids.ts"] = match.group(1) if match else ""

    return found


def cmd_status() -> int:
    found = read_tool_ids()
    if not found:
        print("no files found — run from the repository root", file=sys.stderr)
        return 2

    width = max(len(key) for key in found)
    for key, value in found.items():
        print(f"{key:<{width}}  {value or '(not found)'}")

    distinct = set(found.values())
    if len(distinct) == 1 and "" not in distinct:
        print(f"\nOK — all files agree on {distinct.pop()}")
        return 0
    print("\nMISMATCH — run `set-tool-id.py apply --tool <minted>`", file=sys.stderr)
    return 1


def apply_tool(tool_id: str) -> None:
    data = json.loads(EXECUTA_JSON.read_text(encoding="utf-8"))
    previous = data.get("tool_id", DEV_TOOL_ID)
    data["tool_id"] = tool_id
    EXECUTA_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    text = PYPROJECT.read_text(encoding="utf-8")
    text = re.sub(r'^name\s*=\s*"[^"]+"', f'name = "{tool_id}"', text, count=1, flags=re.MULTILINE)
    text = re.sub(
        r'^"[^"]+"(\s*=\s*"receipts_engine\.plugin:main")',
        f'"{tool_id}"\\1',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    PYPROJECT.write_text(text, encoding="utf-8")

    if IDS_TS.is_file():
        text = IDS_TS.read_text(encoding="utf-8")
        text = re.sub(r'(DEV_TOOL_ID\s*=\s*)"[^"]+"', f'\\1"{tool_id}"', text, count=1)
        IDS_TS.write_text(text, encoding="utf-8")

    print(f"tool  {previous} → {tool_id}")


def apply_skill(skill_id: str) -> None:
    if SKILL_JSON.is_file():
        data = json.loads(SKILL_JSON.read_text(encoding="utf-8"))
        data["tool_id"] = skill_id
        SKILL_JSON.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    if SKILL_MD.is_file():
        text = SKILL_MD.read_text(encoding="utf-8")
        text = re.sub(r"(skill-[A-Za-z0-9_.\-]+)", skill_id, text, count=1)
        SKILL_MD.write_text(text, encoding="utf-8")
    print(f"skill → {skill_id}")


def cmd_apply(args: argparse.Namespace) -> int:
    if not args.tool and not args.skill:
        print("pass --tool and/or --skill", file=sys.stderr)
        return 2
    for value in (args.tool, args.skill):
        if value and not TOOL_ID_RE.match(value):
            print(f"{value!r} does not look like a minted id", file=sys.stderr)
            return 2
    if args.tool:
        apply_tool(args.tool)
    if args.skill:
        apply_skill(args.skill)
    return cmd_status() if args.tool else 0


def cmd_reset() -> int:
    apply_tool(DEV_TOOL_ID)
    apply_skill(DEV_SKILL_ID)
    return cmd_status()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="check that every file agrees")
    apply_parser = sub.add_parser("apply", help="write minted ids into every file")
    apply_parser.add_argument("--tool", help="minted Tool Executa id")
    apply_parser.add_argument("--skill", help="minted Skill Executa id")
    sub.add_parser("reset", help="restore the local-dev ids")

    args = parser.parse_args()
    if args.command == "status":
        return cmd_status()
    if args.command == "apply":
        return cmd_apply(args)
    return cmd_reset()


if __name__ == "__main__":
    raise SystemExit(main())
