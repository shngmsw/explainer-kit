#!/usr/bin/env bash
# 1枚HTML → PDF（Chrome ヘッドレスの印刷機能を使う）
#   ./html2pdf.sh input.html [output.pdf]
# 版面は入力HTMLの @media print が決める。references/print-css.md の型を当てておくこと。
set -euo pipefail

IN="${1:?usage: html2pdf.sh <input.html> [output.pdf]}"
OUT="${2:-${IN%.*}.pdf}"
[ -f "$IN" ] || { echo "error: $IN が無い" >&2; exit 1; }

# Chrome/Chromium の実行パスを優先順位で探す。見つからなければ何も出力せずreturn 1
#   1. CHROME_BIN（エスケープハッチ、実行可能なら最優先）
#   2. PATH上の google-chrome 系（ローカル環境の既定経路）
#   3. macOS の既定インストール先
#   4. Playwright 同梱のChromium（クラウドコンテナ向けフォールバック）
find_chrome() {
    if [ -n "${CHROME_BIN:-}" ] && [ -x "${CHROME_BIN:-}" ]; then
        echo "$CHROME_BIN"; return 0
    fi

    local name
    for name in google-chrome google-chrome-stable chromium chromium-browser chrome; do
        if command -v "$name" >/dev/null 2>&1; then
            command -v "$name"; return 0
        fi
    done

    local mac_default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if [ -x "$mac_default" ]; then
        echo "$mac_default"; return 0
    fi

    local roots=()
    if [ -n "${PLAYWRIGHT_BROWSERS_PATH:-}" ]; then
        roots+=("$PLAYWRIGHT_BROWSERS_PATH")
    else
        roots+=("$HOME/.cache/ms-playwright" "$HOME/Library/Caches/ms-playwright")
    fi
    # フルのChromiumを優先し、headless_shell は最後の手段にする
    local root pat f hits
    shopt -s nullglob
    for pat in "chromium-*/chrome-linux/chrome" \
               "chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium" \
               "chromium_headless_shell-*/chrome-linux/headless_shell"; do
        hits=()
        for root in "${roots[@]}"; do
            for f in "$root"/$pat; do
                [ -x "$f" ] && hits+=("$f")
            done
        done
        if [ "${#hits[@]}" -gt 0 ]; then
            shopt -u nullglob
            # ビルド番号を数値として比較して最大を選ぶ（sort -V 非依存）
            python3 - <<'PY' "${hits[@]}"
import re, sys
paths = sys.argv[1:]

def build_no(p: str) -> int:
    m = re.search(r"-(\d+)(?:/|\\)", p)
    return int(m.group(1)) if m else -1

print(max(paths, key=build_no))
PY
            return 0
        fi
    done
    shopt -u nullglob

    return 1
}

CHROME="$(find_chrome)" || true
[ -n "$CHROME" ] || { echo "error: Chrome/Chromium が見つからない。CHROME_BIN で指定してください" >&2; exit 1; }

ABS="$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$IN")"
"$CHROME" --headless --disable-gpu --no-sandbox --no-pdf-header-footer \
          --print-to-pdf="$OUT" "file://$ABS" 2>/dev/null

[ -f "$OUT" ] || { echo "error: PDF 生成に失敗" >&2; exit 1; }

# ページ数と用紙サイズを報告（無言で妙な版面を納品しないため）
python3 - "$OUT" <<'PY'
import sys, re
d = open(sys.argv[1], "rb").read()
pages = d.count(b"/Type /Page") - d.count(b"/Type /Pages")
mb = re.findall(rb"/MediaBox \[([\d\. ]+)\]", d)
size = ""
if mb:
    v = [float(x) for x in mb[0].split()]
    size = f" / {v[2]/72*25.4:.0f}x{v[3]/72*25.4:.0f}mm"
print(f"出力: {sys.argv[1]}  {len(d)//1024}KB / {pages}ページ{size}")
PY
