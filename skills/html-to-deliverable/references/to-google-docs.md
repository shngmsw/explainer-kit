# Google ドキュメントへの変換

## 必要なもの

`gws` コマンド（[@googleworkspace/cli](https://github.com/googleworkspace/cli)、
Apache-2.0）と OAuth 認証。

```sh
npm install -g @googleworkspace/cli
gws auth login
```

Drive / Docs の REST API を叩ければよいので、`curl` やお使いの言語の SDK でも
同じことができる。以下は `gws` の例で書く。

## docx をアップロードして変換する

docx を Drive にアップロードするとき、`mimeType` に Google ドキュメント形式を
指定すると変換されて入る。ネイティブの Google ドキュメントになるので、そのまま
共同編集できる。

```bash
gws drive files create \
  --json '{"name":"提案書","mimeType":"application/vnd.google-apps.document"}' \
  --upload path/to/file.docx \
  --upload-content-type "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
```

フォルダを指定するなら `"parents":["<folderId>"]` を `--json` に足す。

## 変換で起きること

- **画像は保たれる。** PNG で埋めてあれば劣化しない
- **左ボーダーのカラーボックス（1x1の表）は保たれる。** 表として残る
- **游明朝・游ゴシックは代替フォントになることがある。** 見出しの雰囲気は変わる
- **改ページは保たれる**が、フォント差で位置がずれる

相手に「Google ドキュメントで」と言われた場合はこの経路。**自分たちの作業用に使っている
Markdown やローカル HTML をそのまま渡さない。** 相手が普段使っているツールの形に
合わせて出す。

## docx を経由せず Google ドキュメントを直接作る場合

Docs API の `batchUpdate` を直接叩く方法もある。**図解つきの資料には向かない。**
画像の挿入とカラーボックスは docx 経由のほうが確実で、この方法は挿入位置を
文字インデックスで指定するため、要素が増えるほど計算が煩雑になる。

見出しと本文だけのシンプルな文書や、既存ドキュメントへの追記ならこちらが早い。

空のドキュメントを作る:

```bash
gws drive files create \
  --params '{"uploadType":"multipart"}' \
  --json '{"name":"ドキュメント名","mimeType":"application/vnd.google-apps.document"}'
```

本文を差し込む（`index` は挿入位置の文字オフセット。先頭は 1）:

```bash
gws docs documents batchUpdate \
  --params '{"documentId":"DOC_ID"}' \
  --json '{
    "requests": [
      {"insertText": {"location": {"index": 1}, "text": "本文テキスト\n"}}
    ]
  }'
```

見出しスタイルの適用や範囲指定の書式など、`requests` に指定できる操作は
Docs API のリファレンスを見る。
https://developers.google.com/docs/api/reference/rest/v1/documents/request

**インデックスは挿入するたびにずれる。** 複数の挿入を1回の `batchUpdate` に
まとめる場合は、後ろから前に向かって並べるとずれを考えなくて済む。
