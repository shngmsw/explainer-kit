---
name: html-to-deliverable
description: 1枚もののHTML（zukai-onepager の出力など）を、納品・配布用の Word / PDF / Google ドキュメントに変換する。HTML内のインラインSVG図解はChromeで画像化して埋め込むため、図を作り直す必要がない。「この資料をWordにして」「納品用のドキュメントにして」「PDFにして」「Googleドキュメントに変換して」で起動する。
---

# html-to-deliverable — 1枚HTMLを納品用に清書する

## 目的

**HTML を正本にしたまま**、納品・配布用の形（docx / PDF / Google ドキュメント）を
派生物として出す。図解はHTML内のインラインSVGから自動で画像化するので、
**作図をやり直さない**。HTML を直して再実行すれば納品物も更新される。

## 使う場面

- HTML で説明した資料を、後で読む用・配布用にドキュメント化する
- 相手から Word / Google ドキュメントの形式を指定された
- 印刷して配る必要がある

## 使わない場面

- **対面プレゼン用のスライドが欲しい。** 本文が落ちるので、このスキルの守備範囲
  ではない。スライドは別途作る
- **Markdown が正本の文書。** Markdown から直接変換したほうが早い

## 前提

- `google-chrome`（図のレンダリングとPDF出力に使う）
- `python-docx`, `Pillow`（`pip3 install python-docx Pillow`）
- Google ドキュメント経路のみ `gws` CLI（[@googleworkspace/cli](https://github.com/googleworkspace/cli)）
  と OAuth 認証

## 手順

### 1. 変換先を確認する

どの形式が要るかをユーザーに確認する。複数可。**確認せずに全部作らない**
（Drive を汚す、無駄なファイルが増える）。

### 2. docx を作る

```bash
python3 scripts/html2docx.py <input.html> -o <output.docx>
```

図の枚数と挿入箇所が一致したか、出力メッセージで確認する。ズレたら元HTMLの
`<figure>` 構造を見る。

オプション:
- `--scale N` 図の解像度倍率（既定3。印刷用なら3で十分）
- `--keep-figs DIR` 生成した図PNGを残す（デバッグ用）

### 3. PDF を作る

**先に元HTMLの `@media print` を整える**（`references/print-css.md` の型を当てる）。
これを飛ばすと画面用の版面のまま出て、ページ数が膨らむ。

```bash
scripts/html2pdf.sh <input.html> <output.pdf>
```

ページ数と用紙サイズが出るので、想定と合っているか見る。

### 4. Google ドキュメントにする

docx を作ってから変換アップロードする。手順は `references/to-google-docs.md`。

### 5. 検品する

下のチェックリストを通す。

## 対応するHTML構造

`zukai-onepager` の出力を想定しているが、無い要素は素通りするだけなので
一般的な1枚HTMLでも動く。

| HTML | docx での表現 |
|---|---|
| `<section>` | 章（章ごとに改ページ） |
| `<h2><span class="num">` | 章見出し（番号＋明朝17pt＋下線） |
| `<p class="lead">` | 章のリード文（小さめ・淡色） |
| `<h3>` | 節見出し |
| `<figure><svg>` + `<figcaption>` | PNG画像（本文幅17cm）＋図注 |
| `<table>` | 表（`class="hd"` と `<th>` は見出し扱い） |
| `<div class="card">` | 左ボーダー付きボックス |
| `<span class="gloss">` | 用語ボックス（灰） |
| `<div class="verdict">` | 結論ボックス（青） |
| `<div class="voice">` | 引用（明朝・字下げ＋右寄せの出典） |
| `<strong>` / `<span class="hl">` | 太字 |
| `<span class="c-*">` | 色付き太字（`COLORMAP` で対応色を定義） |

独自の色クラスを使っている場合は、`scripts/html2docx.py` の `COLORMAP` と
`BORDER_ACCENT` に足す。

## 検品チェックリスト

- [ ] 図の枚数と挿入箇所が一致しているか（スクリプトの出力で確認）
- [ ] 図が本文幅に収まり、縦横比が崩れていないか
- [ ] 表の `colspan` が正しくマージされ、文言が二重に入っていないか
- [ ] 空のテーブルが残っていないか（HTMLの装飾用要素が化けることがある）
- [ ] **社外に出す資料の場合、金額・工数・期間など内部情報が混入していないか**
- [ ] PDF のページ数が想定内か（印刷CSSが効いているか）

## 既知の制約

- **webp は使えない。** python-docx が読めない（`UnrecognizedImageError`）。PNG で
  出す。図8枚で約1.4MBになるが、古いWord・Googleドキュメント変換・PDF出力の
  すべてで確実に通ることを優先する
- **CSSレイアウト（flex/grid）は再現されない。** docx 側は段落と表の直列。
  複数カラムのカードは縦に積まれる
- **図はラスタ画像になる。** docx 内でベクタのまま扱いたい場合はこの経路では無理
