# explainer-kit

その分野に詳しくない読者に向けた**説明資料**を作るための Claude Code プラグインです。
図解つきの1枚 HTML を作り、そのまま Word / PDF / Google ドキュメントに変換します。

動画ではなく、読んでもらう文書を作るためのものです。

想定する読者像は「その領域の専門家ではないが、仕事はできる大人」。他部署の担当者、
クライアントの窓口、着任したばかりの管理職あたりです。前提知識は無いが読解力はある、
という相手に向けて書きます。噛み砕くのは内容であって、言葉づかいではありません。

## どんなものができるか

サンプルとして、explainer-kit 自身を explainer-kit で説明した資料を同梱しています。
ファイルは `docs/sample/explainer-kit-onepager.html`（ダウンロードしてブラウザで開くと読めます）。
本文の書き方（用語の即開きと用語集、章ごとの図解、登場要素ごとの色）から、図の lint、
Word / PDF への変換まで、すべてこのプラグインの手順で作ったものです。

### 1枚HTML（zukai-onepager の出力）

![表紙と目次](https://raw.githubusercontent.com/shngmsw/explainer-kit/assets/images/sample-html-cover.png)

章ごとに「言いたいこと1つ」と図解1枚を置き、専門語は使った場所で開きます。

![第1章。見出し・図解・用語ボックス](https://raw.githubusercontent.com/shngmsw/explainer-kit/assets/images/sample-html-section.png)

### 図解（インラインSVG）

図はすべて HTML に直接埋め込んだ SVG です。外部スキル svg-diagram の作図規約で描き、
同梱の lint（`scripts/lint-inline-svg.py`）をエラー0・ワーニング0で通しています。
登場要素（依頼・zukai-onepager・1枚HTML・html-to-deliverable・lint ゲート）には
1色ずつ割り当て、本文と図で同じ色を使います。

![サンプルの図解6枚](https://raw.githubusercontent.com/shngmsw/explainer-kit/assets/images/sample-figures.png)

### Word / PDF（html-to-deliverable の出力）

同じ HTML から `html2docx.py` と `html2pdf.sh` で作った Word と PDF の同じ章です。
図は Chrome で画像化して埋め込まれ、章ごとに改ページされます。

![Word と PDF の同じページ](https://raw.githubusercontent.com/shngmsw/explainer-kit/assets/images/sample-deliverables.png)

Word のフォント指定は游ゴシック・游明朝です。上のプレビューはそれらが無い環境で描画したため
Noto フォントで代替表示しています。

### 自分で再生成する

```sh
# 図の検査（要 svg-diagram）
python3 skills/zukai-onepager/scripts/lint-inline-svg.py docs/sample/explainer-kit-onepager.html

# Word / PDF に変換
python3 skills/html-to-deliverable/scripts/html2docx.py docs/sample/explainer-kit-onepager.html -o explainer-kit-onepager.docx
skills/html-to-deliverable/scripts/html2pdf.sh docs/sample/explainer-kit-onepager.html explainer-kit-onepager.pdf
```

HTML を直して再実行すれば、Word / PDF も作り直されます。

## 収録スキル

| スキル | 用途 |
|---|---|
| `zukai-onepager` | 仕組み・システム・業務フロー・企画・データ構造を、図解つきの1枚 HTML で説明する |
| `html-to-deliverable` | その HTML を Word / PDF / Google ドキュメントに変換する |

2つは工程としてつながっています。HTML を正本にしたまま配布形式を派生させるので、
HTML を直して再実行すれば納品物も更新されます。図を作り直す必要はありません。

## インストール

```
/plugin marketplace add shngmsw/explainer-kit
/plugin install explainer-kit@explainer-kit
```

### 依存

**`zukai-onepager` は外部スキル `svg-diagram` を必要とします。** 図解の作図規約と、
インライン SVG を検査する `svg-lint` をこのスキルから使います。入れずに使うと
lint が終了コード 2 で止まります。

```sh
npx skills add bybit-exchange/svg-diagram -g
```

https://github.com/bybit-exchange/svg-diagram

`html-to-deliverable` は変換先ごとに必要なものが違います。

| 変換先 | 必要なもの |
|---|---|
| Word (docx) | `python-docx`, `Pillow`（`pip3 install python-docx Pillow`）、`google-chrome`（図の画像化） |
| PDF | `google-chrome` |
| Google ドキュメント | 上記に加えて [@googleworkspace/cli](https://github.com/googleworkspace/cli)（`npm i -g @googleworkspace/cli`）と OAuth 認証 |

Google ドキュメント経路は追加のセットアップが要ります。Word / PDF だけなら Chrome と
Python パッケージで動きます。Drive / Docs の REST API を叩ければよいので、CLI の
代わりに `curl` や各言語の SDK を使っても構いません。

## 使い方

Claude Code でそのまま頼みます。

```
この仕組みを、詳しくない人にもわかるように図解して
社内の申請フローを1枚のHTMLにまとめて
```

```
この資料をWordにして
納品用のPDFにして
```

## ライセンス

MIT
