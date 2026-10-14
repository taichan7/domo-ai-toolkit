# pro-code/vendor — 同梱ランタイム

Domo Pro Code 開発シム `domo.js`（ryuu.js 4.6.0・`ryuu.js-4.6.0.LICENSE` 参照）をローカル同梱する。
`index.html` は CDN ではなく `vendor/domo.js` を読む＝**オフライン/社内ネットワークや CDN 障害に依存しない**配布のため。
バージョンを上げる場合は domo.js と対応 LICENSE を差し替え、`index.html` の参照はそのまま（相対パス）。
