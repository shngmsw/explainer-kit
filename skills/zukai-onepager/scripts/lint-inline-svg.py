#!/usr/bin/env python3
"""HTML 内のインラインSVGを svg-diagram の svg-lint で検査する。

zukai-onepager が出力した1枚HTMLから `<svg>…</svg>` をすべて切り出し、
外部スキル svg-diagram (https://github.com/bybit-exchange/svg-diagram) 同梱の
svg-lint にかけて、ハウススタイル違反を原稿の行番号つきで報告する。

使い方:
    python3 lint-inline-svg.py <出力HTML> [<出力HTML> ...]
    python3 lint-inline-svg.py --svg-lint <svg-lint.mjs のパス> <出力HTML>
    python3 lint-inline-svg.py --keep <出力HTML>      # 切り出したSVGを残す

svg-lint の探索順:
    1. --svg-lint <path>
    2. $SVG_DIAGRAM_DIR/tools/svg-lint/bin/svg-lint.mjs
    3. ~/.claude/skills/svg-diagram/tools/svg-lint/bin/svg-lint.mjs
    4. ~/.agents/skills/svg-diagram/tools/svg-lint/bin/svg-lint.mjs

終了コード:
    0  図が1つ以上あり、エラーもワーニングも 0（合格）
    1  エラーまたはワーニングがある。あるいは図が1つも無い（不合格）
    2  svg-diagram か node が見つからない。svg-lint が読めないファイルで落ちた

ワーニングも不合格として扱う。ハウススタイルの合格条件は「エラー 0 かつ
ワーニング 0」であり、「推奨だから」とワーニングを残さない。
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SVG_LINT_REL = Path("tools") / "svg-lint" / "bin" / "svg-lint.mjs"

INSTALL_HINT = (
    "svg-diagram が見つからない。"
    "`npx skills add bybit-exchange/svg-diagram -g` でインストールする"
)

SVG_BLOCK_RE = re.compile(r"<svg\b.*?</svg\s*>", re.S | re.I)
SVG_OPEN_TAG_RE = re.compile(r"<svg\b[^>]*>", re.S | re.I)
SVG_NS = 'xmlns="http://www.w3.org/2000/svg"'


def die(message, code=2):
    print(message, file=sys.stderr)
    sys.exit(code)


def resolve_svg_lint(explicit):
    """svg-lint.mjs の場所を決める。見つからなければ exit 2。"""
    candidates = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    env_dir = os.environ.get("SVG_DIAGRAM_DIR")
    if env_dir:
        candidates.append(Path(env_dir).expanduser() / SVG_LINT_REL)
    home = Path.home()
    candidates.append(home / ".claude" / "skills" / "svg-diagram" / SVG_LINT_REL)
    candidates.append(home / ".agents" / "skills" / "svg-diagram" / SVG_LINT_REL)

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    if explicit:
        die(f"error: --svg-lint のパスにファイルが無い: {explicit}\nhint: {INSTALL_HINT}")
    searched = "\n".join(f"  - {c}" for c in candidates)
    die(f"error: {INSTALL_HINT}\n探した場所:\n{searched}")


def resolve_node():
    node = shutil.which("node")
    if not node:
        die("error: node が見つからない。svg-lint の実行には Node.js が要る")
    return node


def ensure_xmlns(block):
    """開始タグに xmlns が無ければ足す（単体で開けるファイルにするため）。"""
    match = SVG_OPEN_TAG_RE.match(block)
    if not match:
        return block
    open_tag = match.group(0)
    if "xmlns=" in open_tag:
        return block
    patched = open_tag[:-1].rstrip() + " " + SVG_NS + ">"
    return patched + block[match.end():]


def extract(html_path, out_dir):
    """HTML からインラインSVGを切り出す。[(svgファイル, 図番号, 開始行), ...] を返す。"""
    source = html_path.read_text(encoding="utf-8", errors="replace")
    figures = []
    for index, match in enumerate(SVG_BLOCK_RE.finditer(source), start=1):
        line = source.count("\n", 0, match.start()) + 1
        name = f"{html_path.stem}-fig-{index:02d}.svg"
        svg_path = out_dir / name
        svg_path.write_text(ensure_xmlns(match.group(0)) + "\n", encoding="utf-8")
        figures.append((svg_path, index, line))
    return figures


def run_linter(node, svg_lint, svg_paths):
    proc = subprocess.run(
        [str(node), str(svg_lint), "--json", *[str(p) for p in svg_paths]],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 2:
        sys.stderr.write(proc.stderr)
        die("error: svg-lint が終了コード 2 で停止した（ファイルを読めない等）")
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        sys.stderr.write(proc.stderr)
        die("error: svg-lint の JSON 出力を解釈できない")
    return report


def format_repair(repair):
    if not repair:
        return None
    actual = repair.get("actual")
    expected = repair.get("expected")
    hint = repair.get("hint")
    parts = []
    if actual is not None and expected is not None:
        attribute = repair.get("attribute")
        head = f"{attribute}: " if attribute else ""
        parts.append(f"{head}{actual} → {expected}")
    if hint:
        parts.append(str(hint))
    if not parts:
        return None
    return "repair: " + " · ".join(parts)


def main():
    parser = argparse.ArgumentParser(
        description="HTML 内のインラインSVGを svg-diagram の svg-lint で検査する",
    )
    parser.add_argument("html", nargs="+", help="検査する HTML ファイル")
    parser.add_argument("--svg-lint", dest="svg_lint", help="svg-lint.mjs のパスを指定する")
    parser.add_argument(
        "--keep", action="store_true", help="切り出した SVG を消さずに残す"
    )
    args = parser.parse_args()

    svg_lint = resolve_svg_lint(args.svg_lint)
    node = resolve_node()

    html_paths = []
    for raw in args.html:
        path = Path(raw).expanduser()
        if not path.is_file():
            die(f"error: HTML が無い: {path}", code=1)
        html_paths.append(path)

    if args.keep:
        work_dir = Path(tempfile.mkdtemp(prefix="zukai-inline-svg-"))
        cleanup = None
    else:
        cleanup = tempfile.TemporaryDirectory(prefix="zukai-inline-svg-")
        work_dir = Path(cleanup.name)

    try:
        meta = {}
        svg_paths = []
        empty_htmls = []
        for order, html_path in enumerate(html_paths):
            out_dir = work_dir / f"{order:02d}"
            out_dir.mkdir(parents=True, exist_ok=True)
            figures = extract(html_path, out_dir)
            if not figures:
                empty_htmls.append(html_path)
            for svg_path, index, line in figures:
                meta[str(svg_path)] = (html_path, index, line)
                svg_paths.append(svg_path)

        errors = 0
        warnings = 0

        if svg_paths:
            report = run_linter(node, svg_lint, svg_paths)
            for entry in report.get("files", []):
                html_path, index, line = meta.get(
                    entry.get("file", ""), (Path(entry.get("file", "?")), 0, 1)
                )
                label = f"{html_path}:{line}  fig-{index:02d}"
                findings = entry.get("findings") or []
                if not findings:
                    print(f"{label}  ok")
                    continue
                for finding in findings:
                    severity = finding.get("severity", "?")
                    if severity == "error":
                        errors += 1
                    else:
                        warnings += 1
                    check = finding.get("check", "?")
                    code = finding.get("code", "?")
                    message = finding.get("message", "")
                    print(f"{label}  {severity}  {message}  [{check}/{code}]")
                    repair = format_repair(finding.get("repair"))
                    if repair:
                        print(f"    {repair}")

        for html_path in empty_htmls:
            print(f"{html_path}:1  warning  インラインSVGが1つも無い  [zukai/no-figure]")
            print("    repair: 主要セクションすべてに図解を1つ以上置く")

        print()
        if args.keep:
            print(f"切り出した SVG: {work_dir}")
        print(
            f"{len(svg_paths)} figure(s), {errors} error(s), {warnings} warning(s)"
        )

        if empty_htmls:
            print("図の無い HTML は不合格。主要セクションすべてに図解を置く。")
            return 1
        if errors or warnings:
            print("ワーニングも不合格として扱う。エラー 0 かつワーニング 0 が合格。")
            return 1
        return 0
    finally:
        if cleanup is not None:
            cleanup.cleanup()


if __name__ == "__main__":
    sys.exit(main())
