#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""1枚もののHTMLを docx に変換する。図(インラインSVG)はChromeで画像化して埋め込む。

    python3 html2docx.py <input.html> [-o out.docx] [--scale 3] [--keep-figs DIR]

前提: Chrome/Chromium（google-chrome の他、Playwright 同梱のChromiumも自動検出。
      環境変数 CHROME_BIN で明示指定も可） / python-docx / Pillow
対応する構造（zukai-onepager 準拠、無くても動く）:
  section > h2(.num) / p.lead / h3 / p / ul>li / table / figure>svg+figcaption
  span.gloss（用語ボックス）, div.verdict（結論ボックス）, div.card, div.voice
"""
import re, os, sys, json, argparse, subprocess, tempfile, shutil, glob
from html import unescape

try:
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
except ImportError:
    sys.exit("python-docx が必要です: pip3 install python-docx Pillow")

INK      = RGBColor(0x23,0x2A,0x31)
INK_SOFT = RGBColor(0x55,0x60,0x6B)
ACCENT   = RGBColor(0x2E,0x5E,0x8C)
GOTHIC, MINCHO = "游ゴシック", "游明朝"

# HTML の色クラス → docx の色。プロジェクト固有色はここに足す
COLORMAP = {
    "c-kintone": RGBColor(0x2E,0x5E,0x8C), "c-soumu": RGBColor(0x3D,0x7A,0x55),
    "c-keiri":   RGBColor(0x9A,0x6B,0x1F), "c-logi":  RGBColor(0x6B,0x4A,0x8C),
}
BORDER_ACCENT = {"kintone":"2E5E8C","logi":"6B4A8C","outer":"6E7780",
                 "soumu":"3D7A55","keiri":"9A6B1F","alert":"8C3A2E"}


def clean(s):
    return unescape(re.sub(r"\s+", " ", s)).strip()


# ── Chrome/Chromium 実行パスの解決 ──────────────────────────────
def find_chrome():
    """使えるChrome/Chromiumの実行パスを優先順位で探す。無ければNone。

    1. 環境変数 CHROME_BIN（エスケープハッチ、実行可能なら最優先）
    2. PATH上の google-chrome 系（ローカル環境の既定経路）
    3. macOS の既定インストール先
    4. Playwright 同梱のChromium（クラウドコンテナ向けフォールバック）
    """
    env = os.environ.get("CHROME_BIN")
    if env and os.path.isfile(env) and os.access(env, os.X_OK):
        return env

    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        p = shutil.which(name)
        if p:
            return p

    mac_default = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if os.path.isfile(mac_default) and os.access(mac_default, os.X_OK):
        return mac_default

    pw_roots = []
    pw_env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if pw_env:
        pw_roots.append(pw_env)
    else:
        pw_roots += [os.path.expanduser("~/.cache/ms-playwright"),
                     os.path.expanduser("~/Library/Caches/ms-playwright")]
    # フルのChromiumを優先し、headless_shell は最後の手段にする
    patterns = [
        "chromium-*/chrome-linux/chrome",
        "chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium",
        "chromium_headless_shell-*/chrome-linux/headless_shell",
    ]

    def build_no(path):
        """パス中のビルド番号。文字列比較だと 999 > 1194 になるので数値で見る"""
        m = re.search(r"-(\d+)[/\\]", path)
        return int(m.group(1)) if m else -1

    for pat in patterns:
        hits = []
        for root in pw_roots:
            hits += glob.glob(os.path.join(root, pat))
        hits = [h for h in hits if os.access(h, os.X_OK)]
        if hits:
            return max(hits, key=build_no)

    return None


# ── SVG → PNG ────────────────────────────────────────────────
def render_figures(html, outdir, scale=3, chrome=None):
    """<figure> 内のインラインSVGをPNG化。戻り値: [(png_path, caption)]"""
    os.makedirs(outdir, exist_ok=True)
    if chrome is None:
        chrome = find_chrome()
    if not chrome:
        print("  警告: Chrome/Chromium が見つからないため図の画像化をスキップします", file=sys.stderr)
        return []
    style = re.search(r"<style>([\s\S]*?)</style>", html)
    root  = ""
    if style:
        m = re.search(r":root\s*\{([\s\S]*?)\}", style.group(1))
        if m: root = m.group(1)

    figs = re.findall(r"<figure[^>]*>\s*(<svg[\s\S]*?</svg>)([\s\S]*?)</figure>", html)
    results = []
    for i, (svg, rest) in enumerate(figs, 1):
        vb = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
        if not vb:
            print(f"  警告: 図{i} に viewBox が無くスキップ", file=sys.stderr); continue
        w, h = int(float(vb.group(1))), int(float(vb.group(2)))
        page = (f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>'
                f':root{{{root}}}*{{margin:0;padding:0;box-sizing:border-box}}'
                f'html,body{{background:#fff}}'
                f'body{{width:{w}px;height:{h}px;overflow:hidden;'
                f'font-family:"Hiragino Kaku Gothic ProN","Yu Gothic UI","Noto Sans JP","Meiryo",sans-serif;'
                f'font-feature-settings:"palt"}}'
                f'svg{{display:block;width:{w}px;height:{h}px}}</style></head>'
                f'<body>{svg}</body></html>')
        hp = os.path.join(outdir, f"fig{i}.html")
        pp = os.path.join(outdir, f"fig{i}.png")
        open(hp, "w", encoding="utf-8").write(page)
        # headlessの --screenshot は --window-size の高さ通りに描画しないことがあり、
        # コンテンツ下部が欠けることがあるため、高さに余白を足しておく
        # （後段のcropで余白は落とすので最終出力には影響しない）
        pad = max(400, min(h, 1200))
        cmd = [chrome,"--headless","--disable-gpu","--no-sandbox","--hide-scrollbars",
               f"--force-device-scale-factor={scale}", f"--window-size={w},{h+pad}",
               f"--screenshot={pp}", "file://"+os.path.abspath(hp)]
        subprocess.run(cmd, capture_output=True, timeout=120)
        if not os.path.exists(pp):
            print(f"  警告: 図{i} のレンダリングに失敗", file=sys.stderr); continue
        try:  # 最適化。webpは python-docx が読めないので必ずPNGのまま
            from PIL import Image
            im = Image.open(pp).convert("RGB")
            if im.size[1] < h*scale:
                print(f"  警告: 図{i} の描画が指定高さに届いていない（{im.size[1]}px < {h*scale}px）。"
                      f"図が途中で切れている可能性がある", file=sys.stderr)
            im.crop((0,0,min(im.size[0],w*scale),min(im.size[1],h*scale))).save(pp,"PNG",optimize=True)
        except ImportError:
            pass
        cap = clean(re.sub(r"<[^>]+>", "", rest))
        results.append((pp, cap, w/h))
        print(f"  図{i}: {w}x{h} → {os.path.getsize(pp)//1024}KB")
    return results


# ── docx 組み立て ────────────────────────────────────────────
class Builder:
    def __init__(self, doc, usable_cm):
        self.doc, self.W = doc, usable_cm
        # 列の多い表を本文幅より広げる設定（1列増えるごとに WIDEN_STEP ずつ、MAXWIDEN 倍まで）
        self.WIDEN_STEP = 0.14
        self.MAXWIDEN = 1.9
        # 列ごとの文字量の差を幅にどれだけ反映するか（1.0 で文字数に正比例）
        self.WIDTH_EXP = 0.78

    def setfont(self, r, size, bold=False, color=INK, font=GOTHIC):
        r.font.size = Pt(size); r.bold = bold; r.font.color.rgb = color
        r.font.name = font; r._element.rPr.rFonts.set(qn('w:eastAsia'), font)

    def inline(self, frag):
        """<strong>/<span class=hl|c-*>/<code>/<a href> → [(text,bold,color,url)]"""
        frag = re.sub(r"<br\s*/?>", "\n", frag)
        parts, pos = [], 0
        pat = re.compile(r'<(strong|b)>([\s\S]*?)</\1>'
                         r'|<span class="(hl|c-[\w-]+)">([\s\S]*?)</span>'
                         r'|<code>([\s\S]*?)</code>'
                         r'|<a[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>')
        for m in pat.finditer(frag):
            if m.start() > pos:
                t = clean(re.sub(r"<[^>]+>", "", frag[pos:m.start()]))
                if t: parts.append((t, False, INK, None))
            if m.group(1):
                parts.append((clean(re.sub(r"<[^>]+>","",m.group(2))), True, INK, None))
            elif m.group(3):
                cls = m.group(3)
                parts.append((clean(re.sub(r"<[^>]+>","",m.group(4))), True,
                              INK if cls == "hl" else COLORMAP.get(cls, INK), None))
            elif m.group(5) is not None:
                parts.append((clean(m.group(5)), False, ACCENT, None))
            else:
                url = m.group(6)
                txt = clean(re.sub(r"<[^>]+>", "", m.group(7)))
                if url.startswith("#"):
                    parts.append((txt, False, INK, None))
                else:
                    parts.append((txt, False, ACCENT, url))
            pos = m.end()
        if pos < len(frag):
            t = clean(re.sub(r"<[^>]+>", "", frag[pos:]))
            if t: parts.append((t, False, INK, None))
        return [p for p in parts if p[0]]

    def linkrun(self, para, text, url, size=10.5, bold=False, color=None):
        """ハイパーリンク付きの run を段落に足す。"""
        from docx.oxml.shared import qn as _qn
        part = para.part
        r_id = part.relate_to(url,
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
            is_external=True)
        hl = OxmlElement("w:hyperlink"); hl.set(_qn("r:id"), r_id)
        run = para.add_run(text)
        self.setfont(run, size, bold, color or ACCENT)
        run.font.underline = True
        hl.append(run._element)
        para._p.append(hl)
        return run

    def para(self, text, size=10.5, bold=False, color=INK, font=GOTHIC,
             align=None, sb=0, sa=8, ls=1.7, indent=None):
        p = self.doc.add_paragraph()
        if align is not None: p.alignment = align
        pf = p.paragraph_format
        pf.space_before, pf.space_after, pf.line_spacing = Pt(sb), Pt(sa), ls
        if indent: pf.left_indent = Cm(indent)
        for i, l in enumerate(str(text).split("\n")):
            if i: p.add_run().add_break()
            self.setfont(p.add_run(l), size, bold, color, font)
        return p

    def rich(self, parts, size=10.5, sa=8, ls=1.7):
        p = self.doc.add_paragraph()
        p.paragraph_format.space_after, p.paragraph_format.line_spacing = Pt(sa), ls
        for part in parts:
            t, b, c = part[0], part[1], part[2]
            u = part[3] if len(part) > 3 else None
            if u:
                self.linkrun(p, t, u, size, b, c)
                continue
            for i, l in enumerate(t.split("\n")):
                if i: p.add_run().add_break()
                self.setfont(p.add_run(l), size, b, c)
        return p

    def shade(self, cell, hexc):
        e = OxmlElement('w:shd'); e.set(qn('w:val'),'clear'); e.set(qn('w:fill'),hexc)
        cell._tc.get_or_add_tcPr().append(e)

    def borders(self, cell, color="D9DBD4", sz=4, accent=None):
        tcPr = cell._tc.get_or_add_tcPr(); b = OxmlElement('w:tcBorders')
        for side in ('top','left','bottom','right'):
            e = OxmlElement(f'w:{side}'); e.set(qn('w:val'),'single')
            e.set(qn('w:sz'), str(28 if (side=='left' and accent) else sz))
            e.set(qn('w:color'), accent if (side=='left' and accent) else color)
            b.append(e)
        tcPr.append(b)

    def h1(self, num, title, lead="", size=17, level=1):
        """章見出し。Word の Heading スタイルを当ててアウトラインを効かせる。"""
        p = self.doc.add_paragraph(style=f"Heading {level}")
        pf = p.paragraph_format
        pf.space_before, pf.space_after, pf.keep_with_next = Pt(22), Pt(4), True
        if num: self.setfont(p.add_run(f"{num}　"), 11.5, True, ACCENT)
        self.setfont(p.add_run(title), size, True, INK, MINCHO)
        pPr = p._p.get_or_add_pPr(); pbdr = OxmlElement('w:pBdr')
        bt = OxmlElement('w:bottom')
        for k, v in (('w:val','single'),('w:sz','8'),('w:color','2E5E8C'),('w:space','6')):
            bt.set(qn(k), v)
        pbdr.append(bt); pPr.append(pbdr)
        if lead: self.para(lead, size=9.5, color=INK_SOFT, sa=13, ls=1.5)

    def h2(self, title, level=3):
        """小見出し。既定は Heading 3（章が1〜2を使うため）。"""
        p = self.doc.add_paragraph(style=f"Heading {level}")
        pf = p.paragraph_format
        pf.space_before, pf.space_after, pf.keep_with_next = Pt(15), Pt(7), True
        pf.line_spacing = 1.7
        self.setfont(p.add_run(title), 12, True, ACCENT)

    def callout(self, title, body, accent="2E5E8C", bg="EDF3F8", tc=ACCENT):
        t = self.doc.add_table(rows=1, cols=1); t.alignment = WD_TABLE_ALIGNMENT.CENTER
        c = t.cell(0,0); c.width = Cm(self.W); self.shade(c,bg); self.borders(c, accent=accent)
        p = c.paragraphs[0]
        p.paragraph_format.space_after, p.paragraph_format.line_spacing = Pt(3), 1.45
        if title: self.setfont(p.add_run(title), 10.5, True, tc)
        p2 = c.add_paragraph() if title else p
        p2.paragraph_format.line_spacing, p2.paragraph_format.space_after = 1.55, Pt(0)
        for t_, b_, c_, u_ in self.inline(body):
            if u_: self.linkrun(p2, t_, u_, 10, b_, c_)
            else:  self.setfont(p2.add_run(t_), 10, b_, c_)
        self.doc.add_paragraph().paragraph_format.space_after = Pt(5)

    def code(self, text):
        """<pre> をグレー背景の等幅ブロックとして出す"""
        t = self.doc.add_table(rows=1, cols=1); t.alignment = WD_TABLE_ALIGNMENT.CENTER
        c = t.cell(0,0); c.width = Cm(self.W)
        self.shade(c, "F2F1EC"); self.borders(c, accent="D8D2C4")
        lines = text.split("\n")
        for i, line in enumerate(lines):
            p = c.paragraphs[0] if i == 0 else c.add_paragraph()
            pf = p.paragraph_format
            pf.space_after, pf.space_before, pf.line_spacing = Pt(0), Pt(0), 1.3
            r = p.add_run(line if line else " ")
            r.font.name = "Consolas"; r.font.size = Pt(8.5)
            r.font.color.rgb = RGBColor(0x33,0x33,0x33)
            rPr = r._element.get_or_add_rPr()
            rf = rPr.find(qn('w:rFonts'))
            if rf is None:
                rf = OxmlElement('w:rFonts'); rPr.append(rf)
            rf.set(qn('w:eastAsia'), "MS Gothic")
        self.doc.add_paragraph().paragraph_format.space_after = Pt(5)

    def figure(self, path, caption, ratio=None):
        p = self.doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pf = p.paragraph_format
        pf.space_before, pf.space_after, pf.keep_with_next = Pt(6), Pt(4), True
        p.add_run().add_picture(path, width=Cm(self.W))
        if caption:
            cp = self.doc.add_paragraph()
            cp.paragraph_format.space_after, cp.paragraph_format.line_spacing = Pt(12), 1.45
            for t_, b_, c_, u_ in self.inline(caption):
                self.setfont(cp.add_run(t_), 9, b_, INK if b_ else INK_SOFT)

    def autowidths(self, grid, ncol):
        """列ごとの中身の量から幅を配分する。均等割りだと ID 列が無駄に広くなる。"""
        # 列ごとに「1行あたりの文字数」の代表値を取る（見出し行は軽めに見る）
        cols = [[] for _ in range(ncol)]
        for ri, row in enumerate(grid):
            ci = 0
            for kind, attrs, runs in row:
                if ci >= ncol: break
                cs = re.search(r'colspan="(\d+)"', attrs)
                if cs:                      # 結合セルは幅の判断材料にしない
                    ci += int(cs.group(1)); continue
                n = sum(len(r[0]) for r in runs)
                # 見出し行は幅の判断にほぼ使わない（列名の長さより値の量を優先する）
                cols[ci].append(n * (0.25 if (kind == 'h' or ri == 0) else 1.0))
                ci += 1
        # 代表値: 平均寄り。長文が1行だけの列を過大評価しない
        rep = []
        for c in cols:
            vals = [x for x in c if x > 0] or c
            if not vals: rep.append(3.0); continue
            avg = sum(vals)/len(vals); mx = max(vals)
            rep.append(max(2.0, (avg*3 + mx)/4))
        # 列が多い表は本文幅に収めると各列が潰れるので、幅の目標を広げる。
        # 印刷時に右端が切れてもよい前提（画面で読むことを優先する）。
        target = self.W * self.widen(ncol)
        # 差を圧縮しつつ配分する。指数を上げるほど文字量の差が幅に出る
        w = [r ** self.WIDTH_EXP for r in rep]
        tot = sum(w) or 1.0
        raw = [target * x / tot for x in w]
        # 下限・上限を課してから再正規化
        lo, hi = 1.4, target * 0.62
        adj = [min(hi, max(lo, x)) for x in raw]
        t2 = sum(adj) or 1.0
        return [target * x / t2 for x in adj]

    def widen(self, ncol):
        """列数に応じた幅の倍率。5列以上で本文幅を超えて広げる。"""
        if ncol <= 4:
            return 1.0
        return min(self.MAXWIDEN, 1.0 + (ncol - 4) * self.WIDEN_STEP)

    def table(self, frag, widths=None):
        rows = re.findall(r"<tr>([\s\S]*?)</tr>", frag)
        grid = []
        for r in rows:
            cells = re.findall(r'<t([hd])([^>]*)>([\s\S]*?)</t\1>', r)
            grid.append([(k, a, self.inline(v)) for k, a, v in cells])
        if not grid: return
        ncol = max(len(r) for r in grid)
        if widths is None or len(widths) != ncol:
            widths = self.autowidths(grid, ncol)
        t = self.doc.add_table(rows=len(grid), cols=ncol)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        # 指定した列幅を Word / Google ドキュメントに尊重させる
        t.autofit = False
        tblPr = t._tbl.tblPr
        lay = OxmlElement('w:tblLayout'); lay.set(qn('w:type'), 'fixed')
        tblPr.append(lay)
        grid_el = OxmlElement('w:tblGrid')
        for wcm in widths:
            gc = OxmlElement('w:gridCol')
            gc.set(qn('w:w'), str(int(wcm * 567)))   # cm → twips
            grid_el.append(gc)
        t._tbl.insert(1, grid_el)
        for i, row in enumerate(grid):
            ci = 0
            for kind, attrs, runs in row:
                if ci >= ncol: break
                c = t.cell(i, ci); c.width = Cm(widths[ci]); self.borders(c)
                ishead = (kind == 'h') or ('class="hd"' in attrs)
                if ishead: self.shade(c, "F1F2ED")
                cs = re.search(r'colspan="(\d+)"', attrs)
                if cs:
                    span = int(cs.group(1))
                    if ci+span-1 < ncol:
                        c = c.merge(t.cell(i, ci+span-1))
                        for extra in list(c.paragraphs[1:]):   # merge の余剰段落を除去
                            extra._element.getparent().remove(extra._element)
                p = c.paragraphs[0]
                p.paragraph_format.line_spacing = 1.45
                p.paragraph_format.space_before = p.paragraph_format.space_after = Pt(2)
                if not runs: self.setfont(p.add_run(""), 9.5)
                for t_, b_, c_, u_ in runs:
                    if u_: self.linkrun(p, t_, u_, 9.5, b_ or ishead, c_)
                    else:  self.setfont(p.add_run(t_), 9.5, b_ or ishead, c_)
                ci += int(cs.group(1)) if cs else 1
        self.doc.add_paragraph().paragraph_format.space_after = Pt(6)

    def cards(self, frag):
        for m in re.finditer(r'<div class="card"([^>]*)>([\s\S]*?)</div>\s*'
                             r'(?=<div class="card"|</div>)', frag):
            attrs, inner = m.group(1), m.group(2)
            title = re.search(r'<div class="t">([\s\S]*?)</div>', inner)
            bodyp = re.search(r'<p>([\s\S]*?)</p>', inner)
            col = re.search(r'border-left:\s*4px solid var\(--(\w+)\)', attrs)
            accent = BORDER_ACCENT.get(col.group(1), "2E5E8C") if col else "2E5E8C"
            t = self.doc.add_table(rows=1, cols=1); t.alignment = WD_TABLE_ALIGNMENT.CENTER
            c = t.cell(0,0); c.width = Cm(self.W)
            self.borders(c, accent=accent); self.shade(c, "FFFFFF")
            p = c.paragraphs[0]
            p.paragraph_format.space_after, p.paragraph_format.line_spacing = Pt(3), 1.45
            if title:
                self.setfont(p.add_run(clean(re.sub(r'<[^>]+>','',title.group(1)))), 10.5, True, INK)
            if bodyp:
                p2 = c.add_paragraph()
                p2.paragraph_format.line_spacing, p2.paragraph_format.space_after = 1.55, Pt(0)
                for t_, b_, c_, u_ in self.inline(bodyp.group(1)):
                    if u_: self.linkrun(p2, t_, u_, 10, b_, c_)
                    else:  self.setfont(p2.add_run(t_), 10, b_, c_)
            self.doc.add_paragraph().paragraph_format.space_after = Pt(4)


def build(html, figs, out, title_override=None):
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.0)
    sec.top_margin, sec.bottom_margin = Cm(2.2), Cm(2.0)
    usable = 21.0 - 4.0

    st = doc.styles['Normal']
    st.font.name = GOTHIC; st.font.size = Pt(10.5); st.font.color.rgb = INK
    st.element.rPr.rFonts.set(qn('w:eastAsia'), GOTHIC)
    st.paragraph_format.line_spacing = 1.7
    st.paragraph_format.space_after = Pt(8)

    B = Builder(doc, usable)

    # 表紙: .cover があればそこから、無ければ <title> と h1
    cover = re.search(r'<div class="cover">([\s\S]*?)</div>\s*(?=<section|</div>)', html)
    if cover:
        c = cover.group(1)
        to = re.search(r'<div class="to">([\s\S]*?)</div>', c)
        h1t = re.search(r'<h1>([\s\S]*?)</h1>', c)
        meta = re.search(r'<div class="meta">([\s\S]*?)</div>', c)
        if to:   B.para(clean(re.sub(r'<[^>]+>','',to.group(1))), size=10.5, color=INK_SOFT, sb=30, sa=26)
        if h1t:
            t = re.sub(r"<br\s*/?>", "\n", h1t.group(1))
            B.para("\n".join(clean(x) for x in re.sub(r'<[^>]+>','',t).split("\n") if clean(x)),
                   size=21, bold=True, font=MINCHO, sa=22, ls=1.55)
        if meta:
            t = re.sub(r"<br\s*/?>", "\n", meta.group(1))
            B.para("\n".join(clean(x) for x in re.sub(r'<[^>]+>','',t).split("\n") if clean(x)),
                   size=10.5, color=INK_SOFT, ls=1.7)
        # 目次
        toc = re.findall(r'<li><a href="#[^"]*">([\s\S]*?)</a></li>', c)
        if toc:
            B.h2("目次")
            for i, t in enumerate(toc, 1):
                p = doc.add_paragraph()
                p.paragraph_format.space_after = Pt(3)
                p.paragraph_format.line_spacing = 1.5
                p.paragraph_format.left_indent = Cm(0.5)
                B.setfont(p.add_run(f"{i}　"), 10, True, ACCENT)
                B.setfont(p.add_run(clean(t)), 10, False, INK)
    else:
        hdr = re.search(r'<header[^>]*>([\s\S]*?)</header>', html)
        if hdr:
            c = hdr.group(1)
            docid = re.search(r'<p class="docid">([\s\S]*?)</p>', c)
            h1t   = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', c)
            sub   = re.search(r'<p class="sub">([\s\S]*?)</p>', c)
            meta  = re.search(r'<p class="meta">([\s\S]*?)</p>', c)
            if docid:
                B.para(clean(re.sub(r'<[^>]+>','',docid.group(1))),
                       size=9.5, color=INK_SOFT, sb=30, sa=8)
            if h1t:
                t = re.sub(r"<br\s*/?>", "\n", h1t.group(1))
                B.para("\n".join(clean(x) for x in re.sub(r'<[^>]+>','',t).split("\n") if clean(x)),
                       size=21, bold=True, font=MINCHO, sa=14, ls=1.5)
            if sub:
                runs = B.inline(sub.group(1))
                if runs: B.rich(runs, size=11)
            if meta:
                B.para(clean(re.sub(r'<[^>]+>','',meta.group(1))),
                       size=9.5, color=INK_SOFT, sa=10, ls=1.6)
            audm = re.search(r'<div class="audience">([\s\S]*?)</div>', c)
            aud = re.findall(r'<span>([\s\S]*?)</span>', audm.group(1)) if audm else []
            if aud:
                B.callout("この文書の読み方",
                          " ／ ".join(clean(re.sub(r'<[^>]+>','',a_)) for a_ in aud),
                          accent="8A929A", bg="F1F2ED", tc=INK)
            cover = True
        elif title_override:
            B.para(title_override, size=21, bold=True, font=MINCHO, sb=30, sa=22)

    figi = 0
    secs_raw = re.findall(r'<section[^>]*>[\s\S]*?</section>', html)
    has_chapmark = any('class="chapmark"' in x for x in secs_raw)
    secs = re.findall(r'<section[^>]*>([\s\S]*?)</section>', html)
    if not secs:   # section が無い文書は body 全体を1章として扱う
        body = re.search(r'<body[^>]*>([\s\S]*?)</body>', html)
        secs = [body.group(1) if body else html]

    for si, body in enumerate(secs):
        if si or cover: doc.add_page_break()
        h2m = re.search(r'<h2[^>]*>([\s\S]*?)</h2>', body)
        if h2m:
            raw = h2m.group(1)
            numm = re.search(r'<span class="(?:num|n)">([\d.]+)</span>', raw)
            num = numm.group(1) if numm else ""
            title = clean(re.sub(r'<[^>]+>', '', raw.split('</span>')[-1] if numm else raw))
            leadm = re.search(r'<p class="lead">([\s\S]*?)</p>', body)
            raw_sec = secs_raw[si] if si < len(secs_raw) else ""
            is_part = ('class="tabmark"' in raw_sec) or ('class="parttitle"' in raw_sec)
            is_chap = 'class="chapmark"' in raw_sec
            if is_part:
                lv, sz = 1, 24
            elif is_chap:
                lv, sz = 2, 19
            else:
                lv, sz = (3, 15) if has_chapmark else (2, 17)
            B.h1(num, title, clean(re.sub(r'<[^>]+>','',leadm.group(1))) if leadm else "",
                 size=sz, level=lv)

        pat = re.compile(
            r'(?P<h3><h3[^>]*>[\s\S]*?</h3>)'
            r'|(?P<gloss><span class="gloss">[\s\S]*?</span>\s*(?=<|$))'
            r'|(?P<verdict><div class="verdict">\s*<div class="t">[\s\S]*?</div>\s*<p>[\s\S]*?</p>\s*</div>)'
            r'|(?P<fig><figure[^>]*>[\s\S]*?</figure>)'
            r'|(?P<voice><div class="voice">[\s\S]*?</div>)'
            r'|(?P<cards><div class="cards">[\s\S]*?</div>\s*</div>)'
            r'|(?P<table><table[^>]*>[\s\S]*?</table>)'
            r'|(?P<pre><pre[^>]*>[\s\S]*?</pre>)'
            r'|(?P<ul><ul>[\s\S]*?</ul>)'
            r'|(?P<ol><ol>[\s\S]*?</ol>)'
            r'|(?P<p><p(?! class="lead")[^>]*>[\s\S]*?</p>)')
        for m in pat.finditer(body):
            kind, frag = m.lastgroup, m.group(0)
            if kind == 'h3':
                B.h2(clean(re.sub(r'<[^>]+>','',frag)), level=4 if has_chapmark else 3)
            elif kind == 'p':
                inner = re.search(r'<p[^>]*>([\s\S]*?)</p>', frag).group(1)
                runs = B.inline(inner)
                if runs: B.rich(runs, size=9.5 if 'font-size:14px' in frag else 10.5)
            elif kind == 'gloss':
                inner = re.search(r'<span class="gloss">([\s\S]*?)</span>\s*$', frag)
                B.callout("", inner.group(1) if inner else frag,
                          accent="8A929A", bg="F1F2ED", tc=INK)
            elif kind == 'verdict':
                t_ = re.search(r'<div class="t">([\s\S]*?)</div>', frag)
                b_ = re.search(r'<p>([\s\S]*?)</p>', frag)
                B.callout(clean(re.sub(r'<[^>]+>','',t_.group(1))) if t_ else "",
                          b_.group(1) if b_ else "")
            elif kind == 'fig':
                if figi < len(figs):
                    path, cap, ratio = figs[figi]
                    B.figure(path, cap, ratio)
                figi += 1
            elif kind == 'voice':
                v = re.search(r'<div class="voice">([\s\S]*?)<span class="who">([\s\S]*?)</span>', frag)
                if v:
                    B.para(clean(re.sub(r'<[^>]+>','',v.group(1))), size=10.5,
                           font=MINCHO, indent=0.7, sa=1, ls=1.55)
                    B.para(clean(re.sub(r'<[^>]+>','',v.group(2))), size=9, color=INK_SOFT,
                           align=WD_ALIGN_PARAGRAPH.RIGHT, sa=9)
            elif kind == 'cards':
                B.cards(frag)
            elif kind == 'table':
                B.table(frag)
            elif kind == 'pre':
                inner = re.search(r'<pre[^>]*>([\s\S]*?)</pre>', frag).group(1)
                txt = re.sub(r'<[^>]+>', '', inner)
                txt = (txt.replace('&lt;','<').replace('&gt;','>')
                          .replace('&quot;','"').replace('&#39;',"'")
                          .replace('&amp;','&'))
                B.code(txt.strip('\n'))
            elif kind in ('ul','ol'):
                style = 'List Bullet' if kind == 'ul' else 'List Number'
                for li in re.findall(r'<li>([\s\S]*?)</li>', frag):
                    p = doc.add_paragraph(style=style)
                    p.paragraph_format.line_spacing = 1.6
                    p.paragraph_format.space_after = Pt(5)
                    for t_, b_, c_, u_ in B.inline(li):
                        if u_: B.linkrun(p, t_, u_, 10, b_, c_)
                        else:  B.setfont(p.add_run(t_), 10, b_, c_)

    doc.save(out)
    return figi


def main():
    ap = argparse.ArgumentParser(description="1枚HTML → docx（図はSVGから自動画像化）")
    ap.add_argument("input")
    ap.add_argument("-o", "--output")
    ap.add_argument("--scale", type=int, default=3, help="図の解像度倍率 (既定3)")
    ap.add_argument("--keep-figs", help="生成した図PNGを残すディレクトリ")
    a = ap.parse_args()

    chrome = find_chrome()
    if not chrome:
        print("警告: Chrome/Chromium が見つからないため図を画像化できません"
              "（CHROME_BIN で明示指定できます）", file=sys.stderr)

    html = open(a.input, encoding="utf-8").read()
    out = a.output or os.path.splitext(a.input)[0] + ".docx"
    figdir = a.keep_figs or tempfile.mkdtemp(prefix="h2d-")
    try:
        print("図をレンダリング中…")
        figs = render_figures(html, figdir, a.scale, chrome=chrome)
        n = build(html, figs, out)
        size = os.path.getsize(out)
        print(f"\n出力: {out}  ({size//1024}KB)")
        print(f"図: {len(figs)}枚生成 / {n}箇所に挿入")
        if len(figs) != n:
            print(f"  注意: 図の数と挿入箇所が一致しません", file=sys.stderr)
    finally:
        if not a.keep_figs and os.path.isdir(figdir):
            shutil.rmtree(figdir, ignore_errors=True)


if __name__ == "__main__":
    main()
