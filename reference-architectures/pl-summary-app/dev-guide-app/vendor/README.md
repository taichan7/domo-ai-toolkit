# vendor/

Domo Pro Code の同梱 SDK。

- `domo.js` — ryuu.js 4.6.0（Domo App Framework ランタイム）。CDN 参照は禁止（App Studio
  埋め込みで `window.domo` が初期化されず「Domo App Frameworkへ接続できませんでした」に
  なるため、必ず同梱する）。本開発ガイドは Domo API を呼ばない純静的アプリだが、Pro Code
  バンドルの標準構成として同梱している。
- `ryuu.js-4.6.0.LICENSE` — 同 SDK のライセンス原文（来歴用）。
- `ryuu.js-4.6.0.LICENSE.md` — 公開用の同内容コピー。

同じファイルは `pro-code/vendor/` にもある（sha256
`3ce4a7abbc9c05dc8641011d0365c3835add9cd05cde691e93175ffd6afd6ebf`）。公開時は
**`.LICENSE.md` を使い、原文 `.LICENSE` は manifest の `ignore` で公開から除外**する
（CLI の content-type 都合で `.LICENSE`/`.txt` は 0 バイト化するため。pro-code と同一の
対策・2026-10-03 実測）。
