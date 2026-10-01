# 印刷用CSSの型

PDF 化する前に、元HTMLの `@media print` をこの形にしておく。入れないと画面用の
版面のまま出力され、ページ数が無駄に膨らむ。

```css
@media print{
  @page{size:A4; margin:16mm 15mm}
  body{font-size:10.5pt; line-height:1.75; background:#fff}
  .sheet{max-width:none; padding:0}

  /* 章 */
  section{border-bottom:none; padding:18px 0; break-inside:auto}
  section+section{break-before:page}   /* 章ごとに改ページ */
  .cover{break-after:page; padding-top:0}

  /* 分断されると困るものだけ avoid する */
  h2,h3{break-after:avoid}
  figure,table,.card,.voice,.gloss,.verdict{break-inside:avoid}
  figcaption{break-before:avoid}
  tr{break-inside:avoid}

  .toc a{text-decoration:none}
}
```

## 落とし穴

**`section{break-inside:avoid}` を書かない。** 章が1ページに収まらないと Chrome が
逃げ場を探して大量の改ページを打つ。実測で 15ページの文書が 20ページに膨らんだ。
避けるのは figure / table / card のような「途中で切れると意味が壊れる小さい塊」だけ。

**背景色は既定で印刷されない。** カラーボックスの色を残すなら、印刷する人が
ブラウザの「背景のグラフィック」を有効にする必要がある。Chrome ヘッドレスの
`--print-to-pdf` は既定で背景を印刷するので、スクリプト経由なら問題ない。

**`size:A4` を省くと Letter で出ることがある。** 環境のロケール依存なので明示する。

## 確認

`html2pdf.sh` はページ数と用紙サイズを出力する。想定と違ったら CSS を疑う。
