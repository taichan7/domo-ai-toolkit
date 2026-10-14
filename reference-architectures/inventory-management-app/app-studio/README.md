# App Studio snapshot

`app-studio.json` は、参照インスタンスの既存App StudioアプリをDomo Product APIから取得した再配置用スナップショットです。App／Page／Pro Code card／design／outer proxy／inner context の実IDと export 時の実効design versionは `app-studio.json` と [domo-assets.json](../domo-assets.json) を正とし（`export-app-studio` のたびに更新。本書に固定IDを書きません）、別インスタンスでは新しいIDが採番されます。構成の要点は次の通り。

- Card version mode: `FOLLOW_LATEST`（context `designVersion: null`）
- Intrinsic card metadata: `1×1`, `fullpage: false`（Manifestでは参照アプリ同様にキー省略）
- Layout: static、standard 60×82、compact 12×29、終端PAGE_BREAK、カード1枚
- Mobile card behavior: `fitToFrame: false`, `interaction` 既定（未設定＝操作許可）, `hideWrench: true`, `editInAppViewer: true`（`interaction: DISABLED` はPCクリックも殺すため不採用。モバイルの選択枠は100dvh固定CSS＋静的layout＋終端PAGE_BREAKで抑える）
- Source: 参照インスタンスのApp Studio（外向きURLは記載しない。対象は自分のインスタンスで作成する）

Data Appのtheme／navigation、Page stack、standard／compact layout、カード一覧、Pro Code context mappingとexport時の実効design versionを保存しています。利用者・所有者・作成日時・編集ロックなど、別環境へ持ち込まない一時情報は除外しています。SID、token、cookieは含みません。

## 再取得

```bash
cd inventory-management-app
python3 scripts/provision_domo.py export-app-studio
```

## 更新

同一インスタンスへの更新は、`domo-assets.json` に登録済みのApp／Page／Cardを必ず再利用します。

```bash
python3 scripts/provision_domo.py app-studio
```

この処理は既存layoutのwritelockを取得し、対象カードだけをin-place更新してからlockを解放します。登録済みAppまたはCardが見つからない場合は、重複作成せずエラーで停止します。

別インスタンスへ展開する場合は、JSON中のsource IDをそのまま作成IDとして使わず、DataSet／AppDB／Code Engine／Pro Code contextを対象環境のIDへマッピングしてください。Pro Code側の配線（AppDB・DataSet・Code Engine・Workflow）は `python3 scripts/provision_domo.py sync-manifest` が `pro-code/manifest.json` へ書き込みます。App／Page／CardのIDだけは対象インスタンスで新規作成し、`domo-assets.json` へ記録します。
