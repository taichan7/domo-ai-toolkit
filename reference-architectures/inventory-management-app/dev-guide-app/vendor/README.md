# vendor/

同梱している外部ライブラリ。CDN を使わず同梱するのは、Domo の iframe CSP と
オフライン/プレビュー環境の両方で確実に動かすため（版も固定できる）。

- `domo.js` — Domo App Framework (ryuu.js 4.6.0)。`window.domo.navigate()` で
  Domo 内の別画面（データセット/データフロー/アプリ等）へ安全に遷移するために読み込む。
  `http(s)://` の直リンクは iframe のセキュリティ制限に阻まれるため、相対パス＋navigate を使う。
- `ryuu.js-4.6.0.LICENSE` — 上記のライセンス表記。
