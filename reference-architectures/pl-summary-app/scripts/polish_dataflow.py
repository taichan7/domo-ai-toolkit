#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Annotate and section the existing P/L flow without changing data logic.

Uses the same native notes/Section representation as inventory-management-app.
All three GUI coordinate copies stay in lockstep. No DataFlow execution is needed.
"""
from __future__ import annotations
import argparse
import copy
import json
import pathlib
from typing import Any, Dict
import provision_domo as provision
import graph_ui_layout as geometry
SECTIONS = [('prepare', '① 準備｜入力・生成・明細出力', 'Blue', ['IN｜P/L入力データ', 'PY｜損益データ生成', '日付型変更', 'OUT｜P/L明細（店舗×勘定×月）']),
 ('store-ai',
  '② 店舗｜月次集計・短文AI',
  'Purple',
  ['SQL｜要約集計（店舗×月）', 'PY｜AI入力用テキスト結合', '店舗別AIサマリー生成', 'AIエラー列を除去(全社前)']),
 ('company-ai', '③ 全社｜短文AI・要約出力', 'Yellow', ['全社AIサマリー生成', '列を変更', 'OUT｜P/L要約（店舗×月）']),
 ('trend', '④ トレンド｜月次集計・出力', 'Blue', ['SQL｜トレンド集計（店舗×月）', 'OUT｜P/Lトレンド（店舗×月）']),
 ('department', '⑤ 事業部｜集計・出力', 'Green', ['SQL｜事業部別集計（部門×月）', 'OUT｜P/L事業部別（部門×月）'])]
TILES = {'IN｜P/L入力データ': '① 準備｜DataFlowの入力依存を1本に保つ最小seed。実損益の取得ではなく、後段のデモデータ生成を開始するための入力です。',
 'PY｜損益データ生成': '① 準備｜店舗・勘定・月のデモ損益を決定的に合成します。店舗ごとの費用構造や季節性を学ぶ教材です。実顧客データへの接続時はこの生成処理を置き換えます。',
 '日付型変更': '① 準備｜期間の型を明細・月次集計で揃え、日付の並びや比較期間の解釈が下流で食い違わないようにします。',
 'SQL｜要約集計（店舗×月）': '② 店舗｜勘定レベルの明細を店舗×月へ集計。売上・費用・利益・比率・状態ラベルを数値側で確定し、画面とAIが同じ基準を参照します。',
 'PY｜AI入力用テキスト結合': '② 店舗｜確定済みの損益指標をAI入力文へ整えます。店舗用テキストと全社合算テキストを作り、AIに数値の再計算を任せないための境界です。',
 '店舗別AIサマリー生成': '② 店舗｜店舗の損益・予算差異を短文で説明するTextGeneration。概要タブの店舗別AIサマリーに使用し、長文レポートのWorkflowとは別の処理です。',
 'AIエラー列を除去(全社前)': '② 店舗｜店舗AIが付加するDOMO_AI_BATCH_ERROR列を除去し、次の全社AIで同名の補助列が衝突しないようにします。損益指標の列は保持します。',
 '全社AIサマリー生成': '③ 全社｜全店舗の合算テキストから全社の短文経営サマリーを生成。各行に共通の全社視点を持たせ、全社表示の概要タブで利用します。',
 '列を変更': '③ 全社｜中間のAI入力文とエラー補助列を公開出力から外します。UI・Workflowが依存する損益指標と店舗別/全社AIサマリーの列契約を維持します。',
 'SQL｜トレンド集計（店舗×月）': '④ 分析｜店舗×月の売上・純利益を集計してトレンド描画用に実体化。Pro Code側の集計API制限を避け、24か月比較・ランキングの共通データを提供します。',
 'SQL｜事業部別集計（部門×月）': '④ 分析｜収益事業部の売上・売上原価・予算差異を部門×月へ集計。全社の事業部別タブで使い、売上のない間接部門や未配賦の共通費を混在させません。',
 'OUT｜P/L明細（店舗×勘定×月）': '⑤ '
                       '出力｜勘定レベルの明細をREPLACEで公開。長文AIレポートの根拠データとしてsummaryとは別の粒度を保ちます。入力/出力IDと列名を変えないでください。',
 'OUT｜P/L要約（店舗×月）': '⑤ 出力｜店舗×月の損益・状態ラベル・短文AIをREPLACEで公開。UIのsummary '
                    'aliasと親/子Workflowの共通ハブです。長文レポートの保存先はAppDBです。',
 'OUT｜P/Lトレンド（店舗×月）': '⑤ 出力｜店舗×月のトレンド集計をREPLACEで公開。UIのtrend aliasから読み、店舗選択・月次比較・ランキングのドリルダウンに使用します。',
 'OUT｜P/L事業部別（部門×月）': '⑤ 出力｜部門×月の集計をREPLACEで公開。UIのdept '
                      'aliasが参照します。利益と粗利益を混同せず、共通費を勝手に事業部へ配賦しない契約を維持します。'}

def logic(flow: Dict[str, Any]) -> Dict[str, Any]:
    result = {key: copy.deepcopy(flow.get(key)) for key in ('inputs', 'outputs', 'engineProperties', 'settings', 'triggerSettings', 'triggeredByInput', 'enabled', 'paused', 'runState', 'databaseType', 'magic')}
    result['actions'] = [{key: copy.deepcopy(value) for (key, value) in action.items() if key not in ('gui', 'notes', 'tables')} for action in flow['actions']]
    return result

def validate(flow: Dict[str, Any]) -> None:
    elements = flow['gui']['elements']
    assert elements == flow['gui']['canvases']['default']['elements'], 'GUI copies differ'
    sections = [e for e in elements if e['type'] == 'Section']
    assert not geometry.verify_layout(elements), 'shared geometry validation failed'
    assert not geometry.verify_flow(elements, geometry.compute_flow_rank(flow['actions'])), 'shared flow validation failed'
    tiles = {e['id']: e for e in elements if e['type'] == 'Tile'}
    assert set(tiles) == {a['id'] for a in flow['actions']}, 'tile/action mismatch'
    for (i, section) in enumerate(sections):
        for other in sections[i + 1:]:
            assert not (section['x'] < other['x'] + other['width'] and other['x'] < section['x'] + section['width'] and (section['y'] < other['y'] + other['height']) and (other['y'] < section['y'] + section['height'])), 'section overlap'
    for action in flow['actions']:
        tile = tiles[action['id']]
        assert action['notes'] and action['notes'][0]['body'].strip(), 'missing tile note'
        assert action['gui']['x'] == tile['x'] and action['gui']['y'] == tile['y'], 'action GUI differs'
        assert sum((s['x'] + geometry.PAD_L <= tile['x'] and tile['x'] + geometry.TILE_W + geometry.PAD_R <= s['x'] + s['width'] and (s['y'] + geometry.PAD_T <= tile['y']) and (tile['y'] + geometry.TILE_H + geometry.PAD_B <= s['y'] + s['height']) for s in sections)) == 1, 'tile footprint outside its section'
        for upstream in action.get('dependsOn') or []:
            assert tiles[upstream]['x'] < tile['x'], 'flow must run left to right'
        for other in tiles.values():
            if other['id'] != tile['id']:
                assert abs(tile['x'] - other['x']) >= geometry.TILE_W or abs(tile['y'] - other['y']) >= geometry.TILE_H, 'tile overlap'

def annotate(flow: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(flow)
    actions = {a.get('name') or (a.get('dataSource') or {}).get('name'): a for a in result['actions']}
    if set(actions) != set(TILES) or len(result['actions']) != len(TILES):
        raise ValueError('The expected 15-tile P/L contract has changed; not publishing')
    elements = []
    owners = {}
    for (index, (key, name, color, members)) in enumerate(SECTIONS):
        section_id = 'Section-pl-' + key
        elements.append({'id': section_id, 'type': 'Section', 'name': name, 'x': 0, 'y': index * 500, 'width': 1500, 'height': 400, 'backgroundColor': f'var(--colorChart{color}6)'})
        for (column, member) in enumerate(members):
            action = actions[member]
            owners[action['id']] = section_id
            note = name.split('｜')[0] + '｜' + TILES[member].split('｜', 1)[1]
            action['notes'] = [{'x1': None, 'y1': None, 'x2': None, 'y2': None, 'body': note}]
            elements.append({'id': action['id'], 'type': 'Tile', 'x': 64 + column * 220, 'y': index * 500 + 96, 'color': (action.get('gui') or {}).get('color'), 'colorSource': (action.get('gui') or {}).get('colorSource')})
    rank = geometry.compute_flow_rank(result['actions'])
    edges = geometry.edges_from_actions(result['actions'])
    elements = geometry.relayout(elements, rank, edges, max_cols=4)
    sections = {e['id']: e for e in elements if e['type'] == 'Section'}
    tiles = {e['id']: e for e in elements if e['type'] == 'Tile'}
    local = {key: (tile['x'] - sections[owners[key]]['x'], tile['y'] - sections[owners[key]]['y']) for (key, tile) in tiles.items()}
    row_height = max((s['height'] for s in sections.values())) + 56
    for (index, (key, _, _, members)) in enumerate(SECTIONS):
        section = sections['Section-pl-' + key]
        row = (0, 1, 1, 2, 3)[index]
        section['y'] = 16 + row * row_height
        section['x'] = 16
        incoming = [(source, target) for (source, target) in edges if owners[target] == section['id'] and owners[source] != section['id']]
        if incoming:
            section['x'] = max((tiles[source]['x'] + geometry.TILE_W + geometry.COL_GAP - local[target][0] for (source, target) in incoming))
        for (prior_key, _, _, _) in SECTIONS[:index]:
            prior = sections['Section-pl-' + prior_key]
            if prior['y'] == section['y']:
                section['x'] = max(section['x'], prior['x'] + prior['width'] + 56)
        for member in members:
            action = actions[member]
            tile = tiles[action['id']]
            (tile['x'], tile['y']) = (section['x'] + local[action['id']][0], section['y'] + local[action['id']][1])
            action.setdefault('gui', {}).update({'x': tile['x'], 'y': tile['y']})
    result['gui']['elements'] = elements
    result['gui']['useGraphUI'] = True
    result['gui']['canvases']['default']['elements'] = copy.deepcopy(elements)
    validate(result)
    assert logic(result) == logic(flow), 'cosmetic change altered data logic'
    return result

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    client = provision.DomoClient()
    row = next((r for r in provision.list_dataflows(client) if r.get('name') == provision.DATAFLOW_NAME), None)
    if not row:
        raise RuntimeError('The named P/L DataFlow is missing; refusing to guess its id')
    flow_id = provision._id(row)
    before = client.request('GET', f'api/dataprocessing/v1/dataflows/{flow_id}')
    after = annotate(before)
    if args.apply:
        provision._guard_production_write('polish-dataflow')
        latest = client.request('GET', f'api/dataprocessing/v1/dataflows/{flow_id}')
        if logic(latest) != logic(before):
            raise RuntimeError('DataFlow logic changed concurrently; refusing to overwrite it')
        payload = copy.deepcopy(after)
        for action in payload['actions']:
            action.pop('tables', None)
        client.request('PUT', f'api/dataprocessing/v1/dataflows/{flow_id}', payload)
        verified = client.request('GET', f'api/dataprocessing/v1/dataflows/{flow_id}')
        validate(verified)
        if logic(verified) != logic(before):
            raise RuntimeError('DataFlow logic changed after PUT')
        snapshot_path = provision.ROOT / 'dataflow' / '2042.json'
        snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
        snapshot = annotate(snapshot)
        snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'applied': args.apply, 'tilesWithNotes': 15, 'sections': 5, 'logicUnchanged': True, 'runRequired': False}))
if __name__ == '__main__':
    main()
