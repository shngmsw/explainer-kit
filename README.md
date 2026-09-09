# explainer-kit

その分野に詳しくない読者に向けた**説明資料**を作るための Claude Code プラグインです。
図解つきの1枚 HTML を作り、そのまま Word / PDF / Google ドキュメントに変換します。

動画ではなく、読んでもらう文書を作るためのものです。

想定する読者像は「その領域の専門家ではないが、仕事はできる大人」。他部署の担当者、
クライアントの窓口、着任したばかりの管理職あたりです。前提知識は無いが読解力はある、
という相手に向けて書きます。噛み砕くのは内容であって、言葉づかいではありません。

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
