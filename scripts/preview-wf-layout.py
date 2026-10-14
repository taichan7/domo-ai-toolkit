#!/usr/bin/env python3
"""Domo Workflow 定義（designElements）を SVG→HTML で描画するレイアウト目視プレビュー。

使い方:
  python3 scripts/preview-wf-layout.py <definition.json> <out.html>
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless \
    --screenshot=out.png --window-size=1500,1150 out.html

ノード（200x60・type別色）・エッジ（path 折れ線＋矢頭）・条件エッジのラベルチップ（200x40・data.position）を
描画する。`domo-workflow-canvas-layout.md` の §4 オフライン検証（機械チェック validate_layout）と対で、
「美しさ」を人/AI が目視確認するための補助ツール（デプロイ前の最終確認）。
"""

import json, sys, html
d=json.load(open(sys.argv[1]))
if isinstance(d.get("savedJson"),str): d=json.loads(d["savedJson"])
els=d["designElements"]
nodes=[e for e in els if e.get("type") not in ("defaultEdge","conditionEdge")]
edges=[e for e in els if e.get("type") in ("defaultEdge","conditionEdge")]
COL={"rootNode":"#2e7d32","endNode":"#c62828","conditionalGatewayNode":"#f9a825",
     "intermediateCatchEventNode":"#5c6bc0","SUB_FLOW":"#1565c0","DATASET_QUERY_TASK":"#4a90d9",
     "serviceTaskNode":"#90a4ae"}
maxx=max((n["position"]["x"]+220) for n in nodes); maxy=max((n["position"]["y"]+120) for n in nodes)
# also account for label chips
for e in edges:
    p=e["data"].get("position")
    if p: maxx=max(maxx,p["x"]+220); maxy=max(maxy,p["y"]+60)
S=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{maxx}" height="{maxy}" style="background:#fafafa">']
S.append('<defs><marker id="a" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L8,3 L0,6 Z" fill="#777"/></marker></defs>')
for e in edges:
    path=e["data"].get("path") or []
    if len(path)>=2:
        pts=" ".join(f"{x},{y}" for x,y in path)
        S.append(f'<polyline points="{pts}" fill="none" stroke="#777" stroke-width="2" marker-end="url(#a)"/>')
    pos=e["data"].get("position")
    if pos:  # conditional label chip 200x40
        t=html.escape(e["data"].get("title",""))
        S.append(f'<rect x="{pos["x"]}" y="{pos["y"]}" width="200" height="40" rx="20" fill="#eceff1" stroke="#b0bec5"/>')
        S.append(f'<text x="{pos["x"]+100}" y="{pos["y"]+25}" font-size="15" text-anchor="middle" fill="#37474f">{t}</text>')
for n in nodes:
    p=n["position"]; dim=n["data"].get("dimensions",{"width":200,"height":60}); c=COL.get(n["type"],"#90a4ae")
    t=html.escape(n["data"].get("title","")[:22])
    S.append(f'<rect x="{p["x"]}" y="{p["y"]}" width="{dim["width"]}" height="{dim["height"]}" rx="8" fill="#fff" stroke="{c}" stroke-width="3"/>')
    S.append(f'<rect x="{p["x"]}" y="{p["y"]}" width="8" height="{dim["height"]}" rx="2" fill="{c}"/>')
    S.append(f'<text x="{p["x"]+100}" y="{p["y"]+35}" font-size="14" text-anchor="middle" fill="#263238">{t}</text>')
S.append('</svg>')
open(sys.argv[2],"w").write("<!doctype html><meta charset=utf-8><body style=margin:0>"+"".join(S))
print("wrote",sys.argv[2],"size",maxx,"x",maxy)
