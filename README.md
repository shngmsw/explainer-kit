# assets ブランチ

このブランチには、`main` ブランチの README から参照される画像だけを置いています。

plugin marketplace としての explainer-kit は plugin source が `"."` のため、
`main` に置いたファイルはすべて利用者の plugin cache にコピーされます。
Claude Code は marketplace を `--depth 1` かつ `main` のみの shallow clone で
取得するため、画像をこの `assets` ブランチに分離しておけば、
plugin のインストールやキャッシュには含まれず、README の表示にのみ使えます。

## images/

READMEのスクリーンショット等のPNGファイル。
