"""Shared Magic ETL geometry engine, bundled for standalone reference deployment.

Generated from the workspace engine without internal project/person-specific documentation.
Executable statements are unchanged; the task-specific wrapper adds strict edge checks.
"""
from __future__ import annotations
import math
from typing import Any
TILE_W = 176
TILE_H = 112
COL_GAP = 44
ROW_GAP = 48
COL_PITCH = TILE_W + COL_GAP
ROW_PITCH = TILE_H + ROW_GAP
PAD_L = 48
PAD_R = 48
PAD_T = 72
PAD_B = 48
MAX_COLS = 4
BAND_VGAP = 56
SEC_GUTTER = 56
ROW_GUTTER = 56
CANVAS_X0 = 16
CANVAS_Y0 = 16
TARGET_ASPECT = 1.4
TARGET_FLOW_ASPECT = 0.9
FLOW_ASPECT_WEIGHT = 0.35
X_CLUSTER_GAP = 96
Y_CLUSTER_GAP = 72

def _rect(sec: dict[str, Any]) -> tuple[int, int, int, int]:
    return (sec['x'], sec['y'], sec['x'] + sec['width'], sec['y'] + sec['height'])

def _overlap_area(a: tuple, b: tuple) -> int:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return ix * iy

def _cluster(values: list[int], gap: int) -> list[list[int]]:
    uniq = sorted(set(values))
    if not uniq:
        return []
    groups = [[uniq[0]]]
    for v in uniq[1:]:
        if v - groups[-1][-1] <= gap:
            groups[-1].append(v)
        else:
            groups.append([v])
    return groups

def _recover_membership(sections: list[dict], tiles: list[dict]) -> dict[str, list[dict]]:
    by_sec: dict[str, list[dict]] = {s['id']: [] for s in sections}
    orphans: list[str] = []
    for t in tiles:
        (tx, ty) = (t['x'], t['y'])
        containing = [s for s in sections if s['x'] <= tx <= s['x'] + s['width'] and s['y'] <= ty <= s['y'] + s['height']]
        if not containing:
            orphans.append(f"{t['id']}@({tx},{ty})")
            continue
        containing.sort(key=lambda s: s['width'] * s['height'])
        by_sec[containing[0]['id']].append(t)
    if orphans:
        raise ValueError(f'所属シグナル破損: どのセクションにも内包されないタイル {len(orphans)}件: {orphans[:8]}')
    return by_sec

def _layout_section_tiles(tiles: list[dict], rank_of: dict[str, float] | None=None, max_cols: int | None=None) -> tuple[list[tuple[dict, int, int]], int, int]:
    if not tiles:
        return ([], 0, 0)
    mc = MAX_COLS if max_cols is None else max_cols
    if rank_of is not None:
        ranks = sorted({rank_of.get(t['id'], 0.0) for t in tiles})
        col_index = {r: i for (i, r) in enumerate(ranks)}
        cols: dict[int, list[dict]] = {}
        for t in tiles:
            cols.setdefault(col_index[rank_of.get(t['id'], 0.0)], []).append(t)
        ncols = len(ranks)
    else:
        xcols = _cluster([t['x'] for t in tiles], X_CLUSTER_GAP)
        col_of: dict[int, int] = {}
        for (ci, group) in enumerate(xcols):
            for xv in group:
                col_of[xv] = ci
        cols = {}
        for t in tiles:
            cols.setdefault(col_of[t['x']], []).append(t)
        ncols = len(xcols)
    used_cols = min(ncols, mc)
    nbands = (ncols + mc - 1) // mc
    band_rows: list[int] = []
    for b in range(nbands):
        rows_here = 0
        for c in range(b * mc, min((b + 1) * mc, ncols)):
            rows_here = max(rows_here, len(cols.get(c, [])))
        band_rows.append(rows_here)
    band_y0: list[int] = []
    acc = 0
    for b in range(nbands):
        band_y0.append(acc)
        acc += (band_rows[b] - 1) * ROW_PITCH + TILE_H + BAND_VGAP
    content_h = acc - BAND_VGAP
    placed: list[tuple[dict, int, int]] = []
    for c in sorted(cols):
        b = c // mc
        bc = c % mc
        column_tiles = sorted(cols[c], key=lambda t: (t['y'], t['id']))
        for (slot, t) in enumerate(column_tiles):
            lx = bc * COL_PITCH
            ly = band_y0[b] + slot * ROW_PITCH
            placed.append((t, lx, ly))
    content_w = (used_cols - 1) * COL_PITCH + TILE_W
    return (placed, content_w, content_h)

def _pack_sections(sizes: list[tuple[str, int, int]], budget: int) -> dict[str, tuple[int, int]]:
    budget = max(budget, max((w for (_, w, _) in sizes), default=0) + 1)
    sky: list[list[int]] = [[CANVAS_X0, CANVAS_X0 + budget, CANVAS_Y0]]
    placed: dict[str, tuple[int, int]] = {}

    def top_over(x0: int, x1: int) -> int:
        top = CANVAS_Y0
        for (sx0, sx1, sy) in sky:
            if sx1 <= x0 or sx0 >= x1:
                continue
            top = max(top, sy)
        return top

    def add_rect(x0: int, x1: int, new_top: int) -> None:
        out: list[list[int]] = []
        for (sx0, sx1, sy) in sky:
            if sx1 <= x0 or sx0 >= x1:
                out.append([sx0, sx1, sy])
                continue
            if sx0 < x0:
                out.append([sx0, x0, sy])
            if sx1 > x1:
                out.append([x1, sx1, sy])
        out.append([x0, x1, new_top])
        out.sort()
        merged: list[list[int]] = []
        for seg in out:
            if merged and merged[-1][2] == seg[2] and (merged[-1][1] == seg[0]):
                merged[-1][1] = seg[1]
            else:
                merged.append(seg)
        sky[:] = merged
    for (sid, w, h) in sizes:
        best = None
        candidates = sorted({seg[0] for seg in sky} | {CANVAS_X0})
        for x0 in candidates:
            x1 = x0 + w + SEC_GUTTER
            if x1 - SEC_GUTTER > CANVAS_X0 + budget:
                continue
            y0 = top_over(x0, x0 + w + SEC_GUTTER)
            cand = (y0, x0)
            if best is None or cand < best[:2]:
                best = (y0, x0, x1)
        if best is None:
            x0 = CANVAS_X0
            y0 = top_over(x0, x0 + w + SEC_GUTTER)
            best = (y0, x0, x0 + w + SEC_GUTTER)
        (y0, x0, x1) = best
        placed[sid] = (x0, y0)
        add_rect(x0, x1, y0 + h + ROW_GUTTER)
    return placed

def _pack_bbox(sizes: list[tuple[str, int, int]], placed: dict[str, tuple[int, int]]) -> tuple[int, int]:
    dim = {sid: (w, h) for (sid, w, h) in sizes}
    x1 = max((placed[sid][0] + dim[sid][0] for sid in placed), default=CANVAS_X0)
    y1 = max((placed[sid][1] + dim[sid][1] for sid in placed), default=CANVAS_Y0)
    return (x1 - CANVAS_X0, y1 - CANVAS_Y0)

def _best_packing(sizes: list[tuple[str, int, int]]) -> dict[str, tuple[int, int]]:
    sizes = sorted(sizes, key=lambda s: (-s[1] * s[2], -s[2]))
    widest = max((w for (_, w, _) in sizes), default=1)
    total = sum((w + SEC_GUTTER for (_, w, _) in sizes))
    (lo, hi) = (widest, max(widest, total))
    steps = 28
    candidates = sorted({lo + round((hi - lo) * i / steps) for i in range(steps + 1)})
    best = None
    for bud in candidates:
        placed = _pack_sections(sizes, bud)
        (w, h) = _pack_bbox(sizes, placed)
        if w <= 0 or h <= 0:
            continue
        area = w * h
        aspect = w / h
        penalty = 1.0 + 0.05 * abs(math.log(aspect / TARGET_ASPECT))
        score = area * penalty
        if best is None or score < best[0]:
            best = (score, placed)
    return best[1] if best else _pack_sections(sizes, widest)

def _pack_flow_columns(ordered: list[tuple[str, int, int]], height_budget: int) -> dict[str, tuple[int, int]]:
    placed: dict[str, tuple[int, int]] = {}
    x_cursor = CANVAS_X0
    y_cursor = CANVAS_Y0
    col_w = 0
    for (sid, w, h) in ordered:
        if y_cursor > CANVAS_Y0 and y_cursor + h > CANVAS_Y0 + height_budget:
            x_cursor += col_w + SEC_GUTTER
            y_cursor = CANVAS_Y0
            col_w = 0
        placed[sid] = (x_cursor, y_cursor)
        y_cursor += h + ROW_GUTTER
        col_w = max(col_w, w)
    return placed

def _best_flow_packing(sizes: list[tuple[str, int, int]], sec_rank: dict[str, float]) -> dict[str, tuple[int, int]]:
    ordered = sorted(sizes, key=lambda s: (sec_rank.get(s[0], 0.0), -s[1] * s[2]))
    heights = [h for (_, _, h) in ordered]
    tallest = max(heights, default=1)
    total = sum((h + ROW_GUTTER for h in heights))
    (lo, hi) = (tallest, max(tallest, total))
    steps = 28
    candidates = sorted({lo + round((hi - lo) * i / steps) for i in range(steps + 1)})
    best = None
    for bud in candidates:
        placed = _pack_flow_columns(ordered, bud)
        (w, h) = _pack_bbox(sizes, placed)
        if w <= 0 or h <= 0:
            continue
        area = w * h
        aspect = w / h
        penalty = 1.0 + FLOW_ASPECT_WEIGHT * abs(math.log(aspect / TARGET_FLOW_ASPECT))
        score = area * penalty
        if best is None or score < best[0]:
            best = (score, placed)
    return best[1] if best else _pack_flow_columns(ordered, tallest)

def _reorder_sections_within_columns(sec_origin: dict[str, tuple[int, int]], sec_dims: dict[str, tuple[int, int]], by_sec: dict[str, list[dict]], local_pos: dict[str, tuple[int, int]], edges: list[tuple[str, str]], rounds: int=6, exhaustive_cap: int=8) -> dict[str, tuple[int, int]]:
    import itertools
    cols: dict[int, list[str]] = {}
    for (sid, (ox, _oy)) in sec_origin.items():
        cols.setdefault(ox, []).append(sid)
    col_xs = sorted(cols)
    order = {x: sorted(cols[x], key=lambda s: (sec_origin[s][1], s)) for x in col_xs}
    heights = {sid: sec_dims[sid][1] for sid in sec_origin}
    sec_of = {t['id']: sid for (sid, ts) in by_sec.items() for t in ts}
    cross = [(u, v) for (u, v) in edges if u in sec_of and v in sec_of and (sec_of[u] != sec_of[v])]
    tx: dict[str, float] = {}
    rel_y: dict[str, float] = {}
    for (tid, (lx, ly)) in local_pos.items():
        sid = sec_of.get(tid)
        if sid is None:
            continue
        (ox, _oy) = sec_origin[sid]
        tx[tid] = ox + PAD_L + lx + TILE_W / 2.0
        rel_y[tid] = PAD_T + ly + TILE_H / 2.0

    def col_secy(cur: dict[int, list[str]]) -> dict[str, int]:
        sy: dict[str, int] = {}
        for x in col_xs:
            y = CANVAS_Y0
            for sid in cur[x]:
                sy[sid] = y
                y += heights[sid] + ROW_GUTTER
        return sy

    def total_len(sy: dict[str, int]) -> float:
        s = 0.0
        for (u, v) in cross:
            dx = tx[u] - tx[v]
            dy = sy[sec_of[u]] + rel_y[u] - (sy[sec_of[v]] + rel_y[v])
            s += math.hypot(dx, dy)
        return s
    for _ in range(rounds):
        changed = False
        for x in col_xs:
            sids = order[x]
            if len(sids) < 2:
                continue
            if len(sids) <= exhaustive_cap:
                best_perm: list[str] | None = None
                best_key: tuple[float, tuple[str, ...]] | None = None
                for perm in itertools.permutations(sorted(sids)):
                    trial = dict(order)
                    trial[x] = list(perm)
                    key = (round(total_len(col_secy(trial)), 6), perm)
                    if best_key is None or key < best_key:
                        (best_key, best_perm) = (key, list(perm))
                if best_perm is not None and best_perm != sids:
                    order[x] = best_perm
                    changed = True
            else:
                improved = True
                while improved:
                    improved = False
                    for i in range(len(sids) - 1):
                        trial = dict(order)
                        t2 = list(sids)
                        (t2[i], t2[i + 1]) = (t2[i + 1], t2[i])
                        trial[x] = t2
                        if total_len(col_secy(trial)) < total_len(col_secy(order)) - 1e-09:
                            order[x] = sids = t2
                            improved = changed = True
        if not changed:
            break
    sy = col_secy(order)
    return {sid: (sec_origin[sid][0], sy[sid]) for sid in sec_origin}

def compute_flow_rank(actions: list[dict]) -> dict[str, float]:
    depends: dict[str, list[str]] = {a['id']: list(a.get('dependsOn') or []) for a in actions}
    depth: dict[str, float] = {}
    visiting: set[str] = set()

    def _depth(aid: str) -> float:
        if aid in depth:
            return depth[aid]
        ups = depends.get(aid) or []
        if not ups:
            depth[aid] = 0.0
            return 0.0
        if aid in visiting:
            return 0.0
        visiting.add(aid)
        best = 0.0
        for u in ups:
            if u in depends:
                best = max(best, 1.0 + _depth(u))
        visiting.discard(aid)
        depth[aid] = best
        return best
    for a in actions:
        _depth(a['id'])
    return depth

def edges_from_actions(actions: list[dict]) -> list[tuple[str, str]]:
    ids = {a['id'] for a in actions}
    out: list[tuple[str, str]] = []
    for a in actions:
        aid = a['id']
        for u in a.get('dependsOn') or []:
            if u in ids:
                out.append((u, aid))
    return out

def relayout(elements: list[dict], flow_rank: dict[str, float] | None=None, edges: list[tuple[str, str]] | None=None, max_cols: int | None=None) -> list[dict]:
    sections = [e for e in elements if e.get('type') == 'Section']
    tiles = [e for e in elements if e.get('type') == 'Tile']
    if not sections or not tiles:
        return [dict(e) for e in elements]
    by_sec = _recover_membership(sections, tiles)
    sec_size: list[tuple[str, int, int]] = []
    local_pos: dict[str, tuple[int, int]] = {}
    sec_dims: dict[str, tuple[int, int]] = {}
    sec_rank: dict[str, float] = {}
    for s in sections:
        (placed, content_w, content_h) = _layout_section_tiles(by_sec[s['id']], flow_rank, max_cols)
        for (t, lx, ly) in placed:
            local_pos[t['id']] = (lx, ly)
        width = PAD_L + content_w + PAD_R if placed else PAD_L + TILE_W + PAD_R
        height = PAD_T + content_h + PAD_B if placed else PAD_T + TILE_H + PAD_B
        sec_dims[s['id']] = (width, height)
        sec_size.append((s['id'], width, height))
        if flow_rank is not None:
            members = by_sec[s['id']]
            sec_rank[s['id']] = sum((flow_rank.get(t['id'], 0.0) for t in members)) / len(members) if members else 0.0
    if flow_rank is not None:
        sec_origin = _best_flow_packing(sec_size, sec_rank)
        if edges:
            sec_origin = _reorder_sections_within_columns(sec_origin, sec_dims, by_sec, local_pos, edges)
    else:
        sec_origin = _best_packing(sec_size)
    new_elements: list[dict] = []
    for e in elements:
        ne = dict(e)
        if e.get('type') == 'Section':
            (ox, oy) = sec_origin[e['id']]
            (w, h) = sec_dims[e['id']]
            (ne['x'], ne['y'], ne['width'], ne['height']) = (ox, oy, w, h)
        elif e.get('type') == 'Tile':
            sid = _owning_section_id(sections, e)
            if sid is not None and e['id'] in local_pos:
                (ox, oy) = sec_origin[sid]
                (lx, ly) = local_pos[e['id']]
                (ne['x'], ne['y']) = (ox + PAD_L + lx, oy + PAD_T + ly)
        new_elements.append(ne)
    return new_elements

def _owning_section_id(sections: list[dict], tile: dict) -> str | None:
    (tx, ty) = (tile['x'], tile['y'])
    cs = [s for s in sections if s['x'] <= tx <= s['x'] + s['width'] and s['y'] <= ty <= s['y'] + s['height']]
    if not cs:
        return None
    cs.sort(key=lambda s: s['width'] * s['height'])
    return cs[0]['id']

def verify_layout(elements: list[dict]) -> list[str]:
    problems: list[str] = []
    sections = [e for e in elements if e.get('type') == 'Section']
    tiles = [e for e in elements if e.get('type') == 'Tile']
    for i in range(len(sections)):
        for j in range(i + 1, len(sections)):
            ov = _overlap_area(_rect(sections[i]), _rect(sections[j]))
            if ov > 0:
                problems.append(f"V1 セクション重なり area={ov}: {sections[i]['name'][:12]!r} x {sections[j]['name'][:12]!r}")
    for t in tiles:
        sid = _owning_section_id(sections, t)
        if sid is None:
            problems.append(f"V2 タイルがセクション外: {t['id']}@({t['x']},{t['y']})")
            continue
        s = next((s for s in sections if s['id'] == sid))
        if not (s['x'] <= t['x'] and t['x'] + TILE_W <= s['x'] + s['width'] and (s['y'] <= t['y']) and (t['y'] + TILE_H <= s['y'] + s['height'])):
            problems.append(f"V2 タイル本体はみ出し: {t['id']} 本体[{t['x']},{t['y']},{t['x'] + TILE_W},{t['y'] + TILE_H}] ∉ {s['name'][:10]!r}{_rect(s)}")
    trs = [(t['x'], t['y'], t['x'] + TILE_W, t['y'] + TILE_H, t['id']) for t in tiles]
    for i in range(len(trs)):
        for j in range(i + 1, len(trs)):
            if _overlap_area(trs[i][:4], trs[j][:4]) > 0:
                problems.append(f'V3 タイル重なり: {trs[i][4]} x {trs[j][4]}')
    return problems

def verify_flow(elements: list[dict], flow_rank: dict[str, float]) -> list[str]:
    problems: list[str] = []
    sections = [e for e in elements if e.get('type') == 'Section']
    tiles = [e for e in elements if e.get('type') == 'Tile']
    if not flow_rank or not sections:
        return problems
    srank: dict[str, float] = {}
    sx: dict[str, int] = {}
    for s in sections:
        members = [t for t in tiles if _owning_section_id(sections, t) == s['id']]
        if not members:
            continue
        srank[s['id']] = sum((flow_rank.get(t['id'], 0.0) for t in members)) / len(members)
        sx[s['id']] = s['x']
    order = sorted(srank, key=lambda sid: srank[sid])
    for (a, b) in zip(order, order[1:]):
        if srank[b] - srank[a] > 1e-09 and sx[a] - sx[b] > COL_PITCH:
            problems.append(f'V6a flow 逆行: rank {srank[a]:.1f}(x={sx[a]}) が rank {srank[b]:.1f}(x={sx[b]}) より右')
    if tiles:
        dmin = min((flow_rank.get(t['id'], 0.0) for t in tiles))
        dmax = max((flow_rank.get(t['id'], 0.0) for t in tiles))
        if dmax - dmin > 1e-09:
            in_x = [t['x'] for t in tiles if flow_rank.get(t['id'], 0.0) == dmin]
            out_x = [t['x'] for t in tiles if flow_rank.get(t['id'], 0.0) == dmax]
            if in_x and out_x and (min(out_x) < max(in_x)):
                problems.append(f'V6b 入力/出力の左右逆転: 入力最右 x={max(in_x)} ≥ 出力最左 x={min(out_x)}')
    return problems

def bbox(elements: list[dict]) -> tuple[int, int, int, int]:
    xs0 = [e['x'] for e in elements]
    ys0 = [e['y'] for e in elements]
    xs1 = [e['x'] + e.get('width', TILE_W) for e in elements]
    ys1 = [e['y'] + e.get('height', TILE_H) for e in elements]
    return (min(xs0), min(ys0), max(xs1), max(ys1))
