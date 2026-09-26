"""diagram_layout.layout_diagram の配置・経路の検査（2026-09-09 新設・担当H）。

いまの矢印付き図（_diagram_block）で実測された崩れ＝
①箱が辺の関係を無視して全部1行に並ぶ ②SVGが幅に合わせて縮み文字が潰れる
③辺の from/to を番号で書くと結び付かず矢印が1本も描かれない（黙って捨てる）
④箱の中の文字が切れる。
この模块は「配置と経路の計算」だけを純関数として切り出したもので、
描画（SVG化）はしない＝ここでは座標・折れ線・warnings だけを検査する。
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.diagram_layout import Layout, layout_diagram


def _chain_nodes(n: int) -> list[dict]:
    return [{"title": "箱%d" % i, "text": "本文%d" % i} for i in range(n)]


def _chain_edges_by_index(n: int) -> list[dict]:
    return [{"from": i, "to": i + 1} for i in range(n - 1)]


def _box_rect(box):
    return box.x, box.y, box.w, box.h


def _point_strictly_inside(x: float, y: float, box) -> bool:
    return (box.x + 1e-6) < x < (box.x + box.w - 1e-6) and (
        box.y + 1e-6
    ) < y < (box.y + box.h - 1e-6)


def _segment_intersects_box(p1, p2, box) -> bool:
    """線分 p1-p2 が box の矩形と重なりを持つか（軸並行の折れ線区間だけを想定した簡易判定）。"""
    x1, y1 = p1
    x2, y2 = p2
    sx0, sx1 = sorted((x1, x2))
    sy0, sy1 = sorted((y1, y2))
    overlap_x = min(sx1, box.x + box.w) - max(sx0, box.x)
    overlap_y = min(sy1, box.y + box.h) - max(sy0, box.y)
    return overlap_x > 1e-6 and overlap_y > 1e-6


def _point_to_segment_distance(px: float, py: float, a, b) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


# ---------------------------------------------------------------------------
# 2026-09-12（担当H3）：撮影で見つかった残りの粗3件の是正を確認するための道具立て。
# 経路（直線・折れ線・S字）を実際に描かれるとおりの点列に直してから、矩形との
# 交わりを調べる＝軸並行の外接矩形どうしの重なりだけを見る簡易判定だと、斜めの
# 線分が実際には矩形の外を通っていても「交わった」と誤判定するため、一般の
# 線分×矩形の交わり判定を使う（本体コードの安全網と同じ考え方だが、テストは
# 本体の private 関数に頼らず独立に持つ）。
# ---------------------------------------------------------------------------


def _cubic_bezier_point(p0, c1, c2, p3, t: float) -> tuple:
    mt = 1.0 - t
    x = (mt ** 3) * p0[0] + 3 * (mt ** 2) * t * c1[0] + 3 * mt * (t ** 2) * c2[0] + (t ** 3) * p3[0]
    y = (mt ** 3) * p0[1] + 3 * (mt ** 2) * t * c1[1] + 3 * mt * (t ** 2) * c2[1] + (t ** 3) * p3[1]
    return (x, y)


def _route_path_points(route, n: int = 16) -> list:
    """Route が実際に描く点列＝直線・折れ線は points のまま、S字（control が
    入れ子の tuple）は t=0..1 を n 点にサンプリングした曲線上の点にする。"""
    if route.control is not None and isinstance(route.control[0], tuple):
        p0, p3 = route.points[0], route.points[-1]
        c1, c2 = route.control
        return [_cubic_bezier_point(p0, c1, c2, p3, i / (n - 1)) for i in range(n)]
    return list(route.points)


def _point_in_rect(x: float, y: float, rx: float, ry: float, rw: float, rh: float) -> bool:
    return rx <= x <= rx + rw and ry <= y <= ry + rh


def _cross(o, a, b) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _segments_cross(p1, p2, p3, p4) -> bool:
    d1 = _cross(p3, p4, p1)
    d2 = _cross(p3, p4, p2)
    d3 = _cross(p1, p2, p3)
    d4 = _cross(p1, p2, p4)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def _segment_hits_rect(p1, p2, rx: float, ry: float, rw: float, rh: float) -> bool:
    """線分 p1-p2 が矩形(rx,ry,rw,rh)と交わるか（斜めの直線もそのまま扱う一般判定）。"""
    if _point_in_rect(p1[0], p1[1], rx, ry, rw, rh) or _point_in_rect(p2[0], p2[1], rx, ry, rw, rh):
        return True
    corners = [(rx, ry), (rx + rw, ry), (rx + rw, ry + rh), (rx, ry + rh)]
    edges = list(zip(corners, corners[1:] + corners[:1]))
    return any(_segments_cross(p1, p2, a, b) for a, b in edges)


def _route_avoids_box(route, box, pad: float = 0.0) -> bool:
    pts = _route_path_points(route)
    rx, ry, rw, rh = box.x - pad, box.y - pad, box.w + 2 * pad, box.h + 2 * pad
    for a, b in zip(pts, pts[1:]):
        if _segment_hits_rect(a, b, rx, ry, rw, rh):
            return False
    return True


def _estimate_label_width(label: str) -> float:
    """文字幅の見積り（英数は狭く・それ以外は広く＝本体の CHAR_EM_* と同じ考え方の
    テスト側独自の近似。本体の private 関数には頼らない）。"""
    return max(20.0, sum(8.0 if ch.isascii() else 13.0 for ch in label))


def _label_rect(route, height: float = 12.0):
    """ラベルの矩形（文字幅を見積もり×12px高。label_x, label_y を中心とみなす）。"""
    if not route.label:
        return None
    w = _estimate_label_width(route.label)
    return (route.label_x - w / 2.0, route.label_y - height / 2.0, w, height)


def _rects_overlap(a, b) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


# ---------------------------------------------------------------------------
# 2026-09-12（担当H4）：迂回する辺（戻る辺・層を2つ以上飛ばす辺）が、箱の
# 上下中央でなく右側面から出入りするかどうかを確かめるための道具立て。
# ---------------------------------------------------------------------------


def _segments_overlap_collinear(a1, a2, b1, b2, tol: float = 1e-6) -> bool:
    """軸並行の線分 a1-a2 と b1-b2 が、同じ直線上で範囲として重なっているか。

    端点が触れるだけ（区間の重なりが0）は「重なり」に含めない＝2本の経路が
    同じ箱の縁の近くで端点を接する程度は許容し、短い区間を共有して線が
    重なって見える崩れだけを検出する。斜めの線分（S字の制御点を持つ辺）は
    この図では使わないので、ここでは軸並行前提の簡易判定でよい。
    """
    ax1, ay1 = a1
    ax2, ay2 = a2
    bx1, by1 = b1
    bx2, by2 = b2
    a_vertical = abs(ax1 - ax2) < tol
    b_vertical = abs(bx1 - bx2) < tol
    a_horizontal = abs(ay1 - ay2) < tol
    b_horizontal = abs(by1 - by2) < tol
    if a_vertical and b_vertical and abs(ax1 - bx1) < tol:
        lo_a, hi_a = sorted((ay1, ay2))
        lo_b, hi_b = sorted((by1, by2))
        return min(hi_a, hi_b) - max(lo_a, lo_b) > tol
    if a_horizontal and b_horizontal and abs(ay1 - by1) < tol:
        lo_a, hi_a = sorted((ax1, ax2))
        lo_b, hi_b = sorted((bx1, bx2))
        return min(hi_a, hi_b) - max(lo_a, lo_b) > tol
    return False


class TestDiagramLayoutBasics(unittest.TestCase):
    def test_index_from_to_are_linked(self) -> None:
        """①辺の from/to を0始まりの番号で書いても、経路が実際に組まれる。"""
        nodes = _chain_nodes(3)
        edges = [{"from": 0, "to": 1}, {"from": 1, "to": 2}]
        layout = layout_diagram(nodes, edges)
        self.assertEqual(len(layout.routes), 2)
        self.assertEqual(layout.routes[0].from_index, 0)
        self.assertEqual(layout.routes[0].to_index, 1)
        self.assertEqual(layout.routes[1].from_index, 1)
        self.assertEqual(layout.routes[1].to_index, 2)
        self.assertEqual(layout.warnings, [])

    def test_id_from_to_are_linked(self) -> None:
        """②辺の from/to を id 文字列で書いても結び付く。"""
        nodes = [
            {"id": "a", "title": "あなたの依頼"},
            {"id": "b", "title": "フック"},
            {"id": "c", "title": "頁が出る"},
        ]
        edges = [
            {"from": "a", "to": "b", "label": "注入"},
            {"from": "b", "to": "c"},
        ]
        layout = layout_diagram(nodes, edges)
        self.assertEqual(len(layout.routes), 2)
        self.assertEqual((layout.routes[0].from_index, layout.routes[0].to_index), (0, 1))
        self.assertEqual((layout.routes[1].from_index, layout.routes[1].to_index), (1, 2))
        self.assertEqual(layout.routes[0].label, "注入")
        self.assertEqual(layout.warnings, [])

    def test_unknown_reference_goes_to_warnings_not_silently_dropped(self) -> None:
        """③見つからない参照は黙って捨てず、warnings に書いた上で経路を作らない。"""
        nodes = _chain_nodes(2)
        edges = [{"from": 0, "to": "no-such-id"}, {"from": 0, "to": 1}]
        layout = layout_diagram(nodes, edges)
        self.assertEqual(len(layout.routes), 1)
        self.assertTrue(layout.warnings, "不明な参照は warnings に残るはず")
        joined = chr(10).join(layout.warnings)
        self.assertIn("no-such-id", joined)

    def test_chain_of_four_is_single_row(self) -> None:
        """④鎖が4個以下なら横1行に並ぶ。"""
        nodes = _chain_nodes(4)
        edges = _chain_edges_by_index(4)
        layout = layout_diagram(nodes, edges)
        rows = sorted({round(box.y, 3) for box in layout.boxes})
        self.assertEqual(len(rows), 1, "4個の鎖は1行のはず")
        # 左から右へ、鎖の順番どおりに並んでいる
        xs = [box.x for box in layout.boxes]
        self.assertEqual(xs, sorted(xs))

    def test_chain_of_six_is_layered_and_narrower_than_one_row(self) -> None:
        """⑤鎖が6個なら2層以上に分かれ、横1行に並べた場合より幅が狭い。"""
        nodes = _chain_nodes(6)
        edges = _chain_edges_by_index(6)
        layout = layout_diagram(nodes, edges)
        rows = sorted({round(box.y, 3) for box in layout.boxes})
        self.assertGreaterEqual(len(rows), 2, "6個の鎖は2層以上に分かれるはず")

        single_row_layout = layout_diagram(nodes, edges, direction="horizontal")
        self.assertLess(
            layout.width,
            single_row_layout.width,
            "層に分けたほうが横1行より幅が狭いはず",
        )

    def test_fan_out_uses_layered_layout(self) -> None:
        """⑥1つの箱から4本出る扇状は、根と子が別の層に分かれる。"""
        nodes = _chain_nodes(5)
        edges = [{"from": 0, "to": i} for i in range(1, 5)]
        layout = layout_diagram(nodes, edges)
        root_y = layout.boxes[0].y
        child_ys = {round(box.y, 3) for box in layout.boxes[1:]}
        self.assertNotIn(round(root_y, 3), child_ys)
        # 子は根より下（層配置は上から下）
        for box in layout.boxes[1:]:
            self.assertGreater(box.y, root_y)

    def test_skip_layer_route_avoids_intervening_box(self) -> None:
        """辺が層を2つ以上飛ばすとき、間に挟まった箱の中を経路が突っ切らない。

        実測した崩れ＝扇状（起点→4本、max_cols=3）だと4本目の子が2層目に
        落ち、起点→4本目の辺が同じ列の1層目の箱を突き抜けて描かれていた
        （見た目の確認スクリーンショットで発見）。
        """
        nodes = _chain_nodes(5)
        edges = [{"from": 0, "to": i} for i in range(1, 5)]
        layout = layout_diagram(nodes, edges, max_cols=3)
        # 起点→4本目（最後の辺）が、1層目に落ちた箱たちを突っ切っていないか確認する
        last_route = layout.routes[-1]
        self.assertEqual(last_route.from_index, 0)
        self.assertEqual(last_route.to_index, 4)
        target_row = round(layout.boxes[4].y, 3)
        for box in layout.boxes:
            box_row = round(box.y, 3)
            if box_row in (round(layout.boxes[0].y, 3), target_row):
                continue  # 起点自身・目的地自身は対象外
            pts = last_route.points
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                sx0, sx1 = sorted((x1, x2))
                sy0, sy1 = sorted((y1, y2))
                overlap_x = min(sx1, box.x + box.w) - max(sx0, box.x)
                overlap_y = min(sy1, box.y + box.h) - max(sy0, box.y)
                self.assertFalse(
                    overlap_x > 1e-6 and overlap_y > 1e-6,
                    "経路が箱(%.1f,%.1f)を突っ切っている" % (box.x, box.y),
                )

    def test_long_title_wraps_and_grows_box_height(self) -> None:
        """⑦長い題は折り返され、行数が増えたぶん箱の高さも増える。"""
        short = layout_diagram([{"title": "短い題"}], [])
        long_title = "あ" * 40
        long = layout_diagram([{"title": long_title}], [])
        self.assertGreater(len(long.boxes[0].title_lines), 1)
        self.assertGreater(long.boxes[0].h, short.boxes[0].h)
        for line in long.boxes[0].title_lines:
            self.assertLessEqual(len(line), 16)
        # 切れは出さない＝折り返した行を連結すると元の文字列に戻る
        self.assertEqual("".join(long.boxes[0].title_lines), long_title)

    def test_explicit_col_row_takes_priority(self) -> None:
        """⑧col/row の指定があれば、自動配置より優先される（自由配置）。"""
        nodes = [
            {"title": "A", "col": 0, "row": 0},
            {"title": "B", "col": 5, "row": 0},
            {"title": "C", "col": 0, "row": 3},
        ]
        # 辺があっても（層配置が働きそうでも）col/row が勝つ
        edges = [{"from": 0, "to": 1}, {"from": 1, "to": 2}]
        layout = layout_diagram(nodes, edges)
        a, b, c = layout.boxes
        self.assertEqual(round(a.y, 3), round(b.y, 3), "同じ row の箱は同じ高さに並ぶ")
        self.assertGreater(c.y, a.y, "row が大きいほど下に来る")
        self.assertGreater(b.x, a.x, "col が大きいほど右に来る")

    def test_route_endpoint_stops_at_target_border_not_inside(self) -> None:
        """⑨経路の終点は目標の箱の縁で止まり、内部に食い込まない。"""
        nodes = _chain_nodes(5)
        edges = [{"from": 0, "to": i} for i in range(1, 5)]
        layout = layout_diagram(nodes, edges)
        for route in layout.routes:
            target = layout.boxes[route.to_index]
            end_x, end_y = route.points[-1]
            self.assertFalse(
                _point_strictly_inside(end_x, end_y, target),
                "終点(%.1f, %.1f)が箱の内部に食い込んでいる" % (end_x, end_y),
            )
            within_x = target.x - 1e-6 <= end_x <= target.x + target.w + 1e-6
            within_y = target.y - 1e-6 <= end_y <= target.y + target.h + 1e-6
            self.assertTrue(within_x and within_y, "終点は箱の縁の上にあるはず")

    def test_no_edges_eight_nodes_is_three_column_grid(self) -> None:
        """⑩辺なし8個・max_cols=3なら3列の格子に折り返す。"""
        nodes = _chain_nodes(8)
        layout = layout_diagram(nodes, [], max_cols=3)
        self.assertEqual(layout.warnings, [])
        rows: dict[float, int] = {}
        for box in layout.boxes:
            key = round(box.y, 3)
            rows[key] = rows.get(key, 0) + 1
        counts = sorted(rows.values(), reverse=True)
        self.assertEqual(counts[:2], [3, 3], "最初の2行は3個ずつのはず")
        self.assertEqual(sum(counts), 8)
        self.assertLessEqual(max(rows.values()), 3)


class TestDiagramLayoutRobustness(unittest.TestCase):
    def test_empty_nodes_does_not_raise(self) -> None:
        layout = layout_diagram([], [])
        self.assertEqual(layout.boxes, [])
        self.assertEqual(layout.routes, [])
        self.assertIsInstance(layout, Layout)

    def test_malformed_edge_and_bad_font_px_do_not_raise(self) -> None:
        nodes = _chain_nodes(2)
        edges = ["not-a-dict", {"from": 0, "to": 1}]
        layout = layout_diagram(nodes, edges, font_px="not-a-number", max_cols="also-bad")
        self.assertEqual(len(layout.routes), 1)
        self.assertTrue(layout.warnings)
        self.assertEqual(layout.font_px, 14)

    def test_never_more_than_five_boxes_in_a_default_single_row(self) -> None:
        """既定の並べ方では1行に5個以上並べない（鎖は4個まで、格子は max_cols まで）。"""
        nodes = _chain_nodes(4)
        edges = _chain_edges_by_index(4)
        layout = layout_diagram(nodes, edges)
        rows: dict[float, int] = {}
        for box in layout.boxes:
            rows[round(box.y, 3)] = rows.get(round(box.y, 3), 0) + 1
        self.assertLessEqual(max(rows.values()), 4)


class TestDiagramLayoutMaxWidth(unittest.TestCase):
    """2026-09-12（担当H2）：列幅（max_width）に収める専用エンジンの検査。

    実物のスクショで確認された崩れ＝①4箱の図が列幅720pxを超えて横スクロールが
    出た ②英単語（Hermes）が途中で割れた ③鎖4個＋戻る辺の図で層が守られず
    1個目だけ上・残り3個が下に横並びになった、の是正を確認する。
    """

    def test_chain_of_four_fits_max_width_by_going_vertical(self) -> None:
        """①鎖4個は横1行だと720pxを超えるので、縦に積み直して幅に収まる。"""
        nodes = _chain_nodes(4)
        edges = _chain_edges_by_index(4)
        layout = layout_diagram(nodes, edges, max_width=720)
        self.assertLessEqual(layout.width, 720)
        self.assertEqual(layout.orientation, "TB")

    def test_chain_of_four_max_width_has_four_layers(self) -> None:
        """②縦に積み直した鎖4個は、4段（yが4通り）に分かれる＝層が守られる。"""
        nodes = _chain_nodes(4)
        edges = _chain_edges_by_index(4)
        layout = layout_diagram(nodes, edges, max_width=720)
        ys = sorted({round(box.y, 3) for box in layout.boxes})
        self.assertEqual(len(ys), 4, "鎖4個は4段に分かれるはず")

    def test_fan_out_max_width_children_share_layer_and_are_centered(self) -> None:
        """③扇状（1→3）は720pxに収まり、子3つが同じ段に並び、親の中心と子の並びの
        中心が一致する（中央揃え）。"""
        nodes = _chain_nodes(4)
        edges = [{"from": 0, "to": i} for i in range(1, 4)]
        layout = layout_diagram(nodes, edges, max_width=720)
        self.assertLessEqual(layout.width, 720)
        root = layout.boxes[0]
        children = layout.boxes[1:]
        child_ys = {round(box.y, 3) for box in children}
        self.assertEqual(len(child_ys), 1, "子3つは同じ段のはず")
        self.assertNotEqual(round(root.y, 3), next(iter(child_ys)))
        root_center = root.x + root.w / 2.0
        left = min(b.x for b in children)
        right = max(b.x + b.w for b in children)
        children_center = (left + right) / 2.0
        self.assertAlmostEqual(root_center, children_center, delta=1.0)

    def test_english_word_is_not_split_mid_word(self) -> None:
        """④本文中の英単語（Hermes）は、文字数で機械的に折っても途中で割れない。"""
        text = "これは Claude Code と Codex と Hermes の連携を示す図です"
        layout = layout_diagram([{"title": "構成", "text": text}], [])
        joined_lines = layout.boxes[0].body_lines
        for word in ("Claude", "Code", "Codex", "Hermes"):
            self.assertTrue(
                any(word in line for line in joined_lines),
                "%r がどれかの行に丸ごと含まれるはず（行をまたいで割れていないか）" % word,
            )
        # 単語が割れていれば "Herm" だけを含む行ができるはず＝それが無いことも確認する
        for line in joined_lines:
            if "Herm" in line and "Hermes" not in line:
                self.fail("Hermes が途中で割れた: %r" % (joined_lines,))

    def test_back_edge_route_avoids_box_interiors(self) -> None:
        """⑤鎖4個＋戻る辺（4→1）は、層は縦4段のまま保たれ、戻る辺の経路が
        どの箱の内部も突っ切らない。"""
        nodes = _chain_nodes(4)
        edges = _chain_edges_by_index(4) + [{"from": 3, "to": 0}]
        layout = layout_diagram(nodes, edges, max_width=720)
        ys = sorted({round(box.y, 3) for box in layout.boxes})
        self.assertEqual(len(ys), 4, "戻る辺があっても層は4段のまま守られるはず")
        back_route = layout.routes[-1]
        self.assertEqual(back_route.from_index, 3)
        self.assertEqual(back_route.to_index, 0)
        pts = back_route.points
        for a, b in zip(pts, pts[1:]):
            for box in layout.boxes:
                self.assertFalse(
                    _segment_intersects_box(a, b, box),
                    "戻る辺の経路が箱(%.1f,%.1f)を突っ切っている" % (box.x, box.y),
                )

    def test_layer_boxes_share_equal_width(self) -> None:
        """⑥同じ層（同じ段）の箱は幅がそろう。"""
        nodes = _chain_nodes(4)
        edges = [{"from": 0, "to": i} for i in range(1, 4)]
        layout = layout_diagram(nodes, edges, max_width=720)
        widths_by_row: dict[float, set] = {}
        for box in layout.boxes:
            widths_by_row.setdefault(round(box.y, 3), set()).add(round(box.w, 3))
        for row_key, widths in widths_by_row.items():
            self.assertEqual(len(widths), 1, "同じ段の箱は幅がそろうはず（段=%.1f）" % row_key)

    def test_label_is_not_on_the_line(self) -> None:
        """⑦辺のラベルは線分の上ではなく脇に置かれる（最寄りの区間から4pxより遠い）。"""
        nodes = [
            {"id": "repo", "title": "リポジトリ"},
            {"id": "p1", "title": "経路1"},
            {"id": "p2", "title": "経路2"},
        ]
        edges = [
            {"from": "repo", "to": "p1", "label": "push"},
            {"from": "repo", "to": "p2", "label": "fetch"},
        ]
        layout = layout_diagram(nodes, edges, max_width=720)
        for route in layout.routes:
            if not route.label:
                continue
            dmin = min(
                _point_to_segment_distance(route.label_x, route.label_y, a, b)
                for a, b in zip(route.points, route.points[1:])
            )
            self.assertGreater(
                dmin, 4.0, "ラベル(%r)が線の上に乗っている" % route.label
            )

    def test_max_width_none_keeps_legacy_behavior(self) -> None:
        """⑧max_width を渡さなければ、従来（既存14本が担保する）挙動と同じになる。"""
        nodes = _chain_nodes(4)
        edges = _chain_edges_by_index(4)
        legacy = layout_diagram(nodes, edges)
        explicit_none = layout_diagram(nodes, edges, max_width=None)
        self.assertEqual(legacy.width, explicit_none.width)
        self.assertEqual(legacy.height, explicit_none.height)
        self.assertEqual(len(legacy.boxes), len(explicit_none.boxes))
        for a, b in zip(legacy.boxes, explicit_none.boxes):
            self.assertEqual((a.x, a.y, a.w, a.h), (b.x, b.y, b.w, b.h))
        for a, b in zip(legacy.routes, explicit_none.routes):
            self.assertEqual(a.points, b.points)

    def test_user_reported_repo_diagram_fits_max_width(self) -> None:
        """⑨ユーザーの実例＝リポジトリ→3経路／リポジトリ→origin→別の機械（本文つき）が
        max_width=720 で幅720px以下に収まる。"""
        nodes = [
            {"id": "repo", "title": "リポジトリ", "text": "sample-repo"},
            {"id": "path1", "title": "経路1", "text": "ローカルの作業コピー"},
            {"id": "path2", "title": "経路2", "text": "別ブランチへの反映"},
            {"id": "origin", "title": "origin", "text": "GitHubのリモート"},
            {
                "id": "another",
                "title": "別の機械",
                "text": "originを経由して取得する別のPC",
            },
        ]
        edges = [
            {"from": "repo", "to": "path1", "label": "作業"},
            {"from": "repo", "to": "path2", "label": "反映"},
            {"from": "repo", "to": "origin", "label": "push/pull"},
            {"from": "origin", "to": "another", "label": "clone"},
        ]
        layout = layout_diagram(nodes, edges, max_width=720)
        self.assertLessEqual(layout.width, 720)
        self.assertEqual(len(layout.routes), 4)
        self.assertEqual(layout.warnings, [])


class TestDiagramLayoutH3Fixes(unittest.TestCase):
    """2026-09-12（担当H3）：完成頁を撮影して見つかった残りの粗3件の是正を確認する。

    ①辺のラベルが箱の縁に触れる（figs 1・2・4） ②折り返した段への辺が別の箱
    の裏を通る（fig 3の扇状） ③ラベル付きの層間は60px以上・無しは44pxのまま。
    """

    def test_fig1_labels_do_not_overlap_any_box(self) -> None:
        """①図1の定義＝ラベルの矩形がどの箱の矩形とも交わらない。"""
        nodes = [
            {"id": "repo", "title": "この機械のリポジトリ", "text": "フックの実体"},
            {"id": "local", "title": "この機械の3経路", "text": "Claude Code・Codex・Hermes"},
            {"id": "origin", "title": "origin の master", "text": "98a916d"},
            {"id": "other", "title": "別の機械・クラウド", "text": "pull で受け取る"},
        ]
        edges = [
            {"from": "repo", "to": "local", "label": "毎回実行"},
            {"from": "repo", "to": "origin", "label": "push 11件"},
            {"from": "origin", "to": "other", "label": "pull"},
        ]
        layout = layout_diagram(nodes, edges, max_width=720)
        for route in layout.routes:
            rect = _label_rect(route)
            self.assertIsNotNone(rect, "この図の辺はすべてラベルがあるはず")
            for box in layout.boxes:
                self.assertFalse(
                    _rects_overlap(rect, (box.x, box.y, box.w, box.h)),
                    "ラベル(%r)が箱と重なっている" % (route.label,),
                )

    def test_fig2_labels_do_not_overlap_any_box(self) -> None:
        """①図2の定義（鎖＋戻る辺）でも同様。"""
        nodes = [
            {"num": "1", "title": "定義ファイル", "text": "箱と辺を宣言"},
            {"num": "2", "title": "配置の計算", "text": "層を決めて置く"},
            {"num": "3", "title": "描画", "text": "箱・矢印・ラベル"},
            {"num": "4", "title": "検品と撮影", "text": "1280と390で撮る"},
        ]
        edges = [
            {"from": 0, "to": 1, "label": "渡す"},
            {"from": 1, "to": 2, "label": "位置と経路"},
            {"from": 2, "to": 3, "label": "HTML"},
            {"from": 3, "to": 1, "label": "崩れたら直す"},
        ]
        layout = layout_diagram(nodes, edges, max_width=720)
        for route in layout.routes:
            rect = _label_rect(route)
            self.assertIsNotNone(rect, "この図の辺はすべてラベルがあるはず")
            for box in layout.boxes:
                self.assertFalse(
                    _rects_overlap(rect, (box.x, box.y, box.w, box.h)),
                    "ラベル(%r)が箱と重なっている" % (route.label,),
                )

    def test_fig3_route_to_wrapped_child_avoids_sibling_box(self) -> None:
        """②図3の定義＝「元資料」→「用語の統一」（2段目に折り返した子）の経路が、
        1段目に残った「数値の照合」の矩形を（サンプリングして確認して）突っ切らない。"""
        nodes = [
            {"title": "元資料", "text": "スライド40枚"},
            {"title": "主張の原子化", "text": "1文1主張"},
            {"title": "数値の照合", "text": "出所と単位"},
            {"title": "図の読み取り", "text": "表と図"},
            {"title": "用語の統一", "text": "略記を揃える"},
        ]
        edges = [{"from": 0, "to": i} for i in range(1, 5)]
        layout = layout_diagram(nodes, edges, max_width=720)
        route = next(r for r in layout.routes if r.from_index == 0 and r.to_index == 4)
        sibling = layout.boxes[2]  # 「数値の照合」＝1段目に残った子
        self.assertTrue(
            _route_avoids_box(route, sibling),
            "元資料→用語の統一の経路が数値の照合を突っ切っている",
        )

    def test_labeled_layer_gap_is_wider_than_unlabeled(self) -> None:
        """③ラベル付きの層間は60px以上に広がり、ラベルの無い層間は44pxのまま。

        鎖ではなく枝分かれ（根+3子）にして必ずTB配置にする（2子だと『枝分かれの
        無い一本の鎖』として横1行になってしまうため）。
        """
        nodes = _chain_nodes(4)
        labeled_edges = [
            {"from": 0, "to": 1, "label": "あ"},
            {"from": 0, "to": 2, "label": "い"},
            {"from": 0, "to": 3, "label": "う"},
        ]
        plain_edges = [{"from": 0, "to": i} for i in range(1, 4)]

        labeled = layout_diagram(nodes, labeled_edges, max_width=720)
        plain = layout_diagram(nodes, plain_edges, max_width=720)
        self.assertEqual(labeled.orientation, "TB")
        self.assertEqual(plain.orientation, "TB")

        root_bottom_labeled = labeled.boxes[0].y + labeled.boxes[0].h
        child_top_labeled = labeled.boxes[1].y
        gap_labeled = child_top_labeled - root_bottom_labeled

        root_bottom_plain = plain.boxes[0].y + plain.boxes[0].h
        child_top_plain = plain.boxes[1].y
        gap_plain = child_top_plain - root_bottom_plain

        self.assertGreaterEqual(gap_labeled, 60.0, "ラベル付きの層間は60px以上のはず")
        self.assertAlmostEqual(gap_plain, 44.0, delta=1e-6, msg="ラベル無しの層間は44pxのまま")

    def test_arbitrary_dag_all_routes_avoid_other_boxes(self) -> None:
        """④安全網＝図4の定義（6箱 2→2→2）で、すべての辺の経路（サンプリングして
        確認）が出発・到着以外の箱を突っ切らない。"""
        nodes = [
            {"id": "a", "title": "取り込み", "text": "資料を読む"},
            {"id": "b", "title": "検索", "text": "一次資料を探す"},
            {"id": "c", "title": "多視点の批評", "text": "10本のレンズ"},
            {"id": "d", "title": "敵対的検証", "text": "反証を試す"},
            {"id": "e", "title": "仕分け", "text": "重み付け"},
            {"id": "f", "title": "採点", "text": "段階で示す"},
        ]
        edges = [
            {"from": "a", "to": "c", "label": "主張"},
            {"from": "b", "to": "c"},
            {"from": "a", "to": "d"},
            {"from": "b", "to": "d", "label": "出所"},
            {"from": "c", "to": "e"},
            {"from": "d", "to": "e"},
            {"from": "c", "to": "f"},
            {"from": "d", "to": "f"},
        ]
        layout = layout_diagram(nodes, edges, max_width=720)
        self.assertEqual(layout.warnings, [])
        for route in layout.routes:
            for idx, box in enumerate(layout.boxes):
                if idx in (route.from_index, route.to_index):
                    continue
                self.assertTrue(
                    _route_avoids_box(route, box),
                    "辺(%d->%d)の経路が箱%dを突っ切っている" % (route.from_index, route.to_index, idx),
                )


class TestDiagramLayoutH4Fixes(unittest.TestCase):
    """2026-09-12（担当H4）：迂回する辺（戻る辺・層を2つ以上飛ばす辺）が箱の
    上下中央でなく右側面から出入りし、順方向の辺と出入口を共有しない・
    層間の隙間を横に走らない・複数本あれば縦線をずらす、の是正を確認する。

    図2（鎖4個＋戻る辺 3→1）・図3（扇状で2段目に折り返した子への辺）は、
    H3のテスト（TestDiagramLayoutH3Fixes）と同じ定義を使う。
    """

    def test_fig2_back_edge_exits_and_enters_via_box_right_edge(self) -> None:
        """①図2（戻る辺3→1）で、経路の始点xは出発の箱の右端、終点xは到着の
        箱の右端に等しい（上下中央からではない）。"""
        nodes = [
            {"num": "1", "title": "定義ファイル", "text": "箱と辺を宣言"},
            {"num": "2", "title": "配置の計算", "text": "層を決めて置く"},
            {"num": "3", "title": "描画", "text": "箱・矢印・ラベル"},
            {"num": "4", "title": "検品と撮影", "text": "1280と390で撮る"},
        ]
        edges = [
            {"from": 0, "to": 1, "label": "渡す"},
            {"from": 1, "to": 2, "label": "位置と経路"},
            {"from": 2, "to": 3, "label": "HTML"},
            {"from": 3, "to": 1, "label": "崩れたら直す"},
        ]
        layout = layout_diagram(nodes, edges, max_width=720)
        back_route = next(r for r in layout.routes if r.from_index == 3 and r.to_index == 1)
        source_box = layout.boxes[3]
        target_box = layout.boxes[1]
        start_x, _ = back_route.points[0]
        end_x, _ = back_route.points[-1]
        self.assertAlmostEqual(start_x, source_box.x + source_box.w, delta=1e-6)
        self.assertAlmostEqual(end_x, target_box.x + target_box.w, delta=1e-6)

    def test_fig2_back_edge_route_does_not_overlap_forward_route(self) -> None:
        """②図2で、戻る辺(3→1)の経路と順方向(1→2)の経路が、どの区間でも
        重ならない（旧経路は上下中央の出入口を共有し短い区間で重なっていた）。"""
        nodes = [
            {"num": "1", "title": "定義ファイル", "text": "箱と辺を宣言"},
            {"num": "2", "title": "配置の計算", "text": "層を決めて置く"},
            {"num": "3", "title": "描画", "text": "箱・矢印・ラベル"},
            {"num": "4", "title": "検品と撮影", "text": "1280と390で撮る"},
        ]
        edges = [
            {"from": 0, "to": 1, "label": "渡す"},
            {"from": 1, "to": 2, "label": "位置と経路"},
            {"from": 2, "to": 3, "label": "HTML"},
            {"from": 3, "to": 1, "label": "崩れたら直す"},
        ]
        layout = layout_diagram(nodes, edges, max_width=720)
        back_route = next(r for r in layout.routes if r.from_index == 3 and r.to_index == 1)
        forward_route = next(r for r in layout.routes if r.from_index == 1 and r.to_index == 2)
        for a1, a2 in zip(back_route.points, back_route.points[1:]):
            for b1, b2 in zip(forward_route.points, forward_route.points[1:]):
                self.assertFalse(
                    _segments_overlap_collinear(a1, a2, b1, b2),
                    "戻る辺(3→1)と順方向(1→2)の経路区間が重なっている: %r / %r" % ((a1, a2), (b1, b2)),
                )

    def test_fig3_route_has_no_horizontal_segment_crossing_the_layer_gap(self) -> None:
        """③図3（元資料→用語の統一＝2段目に折り返した子）の経路は、層間の隙間
        （root下端〜1段目の子の上端）を横切る横線を持たない（側面の縦線1本を
        通るだけで、隙間を横に走って迂回しない）。"""
        nodes = [
            {"title": "元資料", "text": "スライド40枚"},
            {"title": "主張の原子化", "text": "1文1主張"},
            {"title": "数値の照合", "text": "出所と単位"},
            {"title": "図の読み取り", "text": "表と図"},
            {"title": "用語の統一", "text": "略記を揃える"},
        ]
        edges = [{"from": 0, "to": i} for i in range(1, 5)]
        layout = layout_diagram(nodes, edges, max_width=720)
        route = next(r for r in layout.routes if r.from_index == 0 and r.to_index == 4)
        root = layout.boxes[0]
        # 1段目に残った子（root・折り返した4番目以外）の上端＝層間の隙間の下端
        row1_top = min(
            box.y for idx, box in enumerate(layout.boxes) if idx not in (0, 4)
        )
        gap_lo, gap_hi = root.y + root.h, row1_top
        self.assertLess(gap_lo, gap_hi, "root と1段目の子の間に隙間があるはず")
        for (x1, y1), (x2, y2) in zip(route.points, route.points[1:]):
            is_horizontal = abs(y1 - y2) < 1e-6 and abs(x1 - x2) > 1e-6
            if not is_horizontal:
                continue
            self.assertFalse(
                gap_lo + 1e-6 < y1 < gap_hi - 1e-6,
                "横線(y=%.1f)が層間の隙間(%.1f〜%.1f)を横切っている" % (y1, gap_lo, gap_hi),
            )

    def test_two_detour_edges_use_different_vertical_lines(self) -> None:
        """④迂回する辺が2本ある図（鎖5個＋戻る辺2本）で、縦線のxが異なる
        （同じ側面の縦線を重ねて通らない）。"""
        nodes = _chain_nodes(5)
        edges = _chain_edges_by_index(5) + [
            {"from": 3, "to": 0},
            {"from": 4, "to": 0},
        ]
        layout = layout_diagram(nodes, edges, max_width=720)
        detours = [r for r in layout.routes if r.to_index == 0 and r.from_index in (3, 4)]
        self.assertEqual(len(detours), 2, "戻る辺2本の経路が見つかるはず")
        for route in detours:
            self.assertEqual(len(route.points), 4, "迂回の経路は4点のはず")
        side_xs = {round(r.points[1][0], 3) for r in detours}
        self.assertEqual(len(side_xs), 2, "2本の迂回線が同じ縦線を重ねて通ってはいけない")


class TestLongEdgesAvoidBoxesRegression(unittest.TestCase):
    """2026-09-23 に、位置を指定した7つの箱の図で見つかった、迂回線と注記の重なりを固定する。"""

    def test_long_edges_and_labels_avoid_policy_graph_boxes(self) -> None:
        nodes = [
            {"id": "P1", "title": "対象範囲・予定枠・期待効果・運用体制", "col": 0, "row": 0},
            {"id": "V1", "title": "全ての利用者の機会を公平に確保", "col": 1, "row": 0},
            {"id": "Q1", "title": "人材不足・効果未検証・現場負担", "col": 0, "row": 1},
            {"id": "Q2", "title": "人材不足・効果未検証・公平な機会", "col": 1, "row": 1},
            {"id": "R1", "title": "週10時間の全店実施を当面維持", "col": 0, "row": 2},
            {"id": "R2", "title": "継続的に評価して見直す", "col": 1, "row": 2},
            {"id": "R3", "title": "関係者調査と利用者への影響評価", "col": 1, "row": 3},
        ]
        edges = [
            {"from": "P1", "to": "R1", "label": "A1a"},
            {"from": "V1", "to": "R1", "label": "A1b"},
            {"from": "Q1", "to": "R1", "label": "A2"},
            {"from": "Q2", "to": "R2", "label": "A3"},
            {"from": "R2", "to": "R3", "label": "A4"},
        ]
        layout = layout_diagram(nodes, edges, max_width=720)
        self.assertEqual(layout.warnings, [])
        for route in layout.routes:
            for index, box in enumerate(layout.boxes):
                if index not in (route.from_index, route.to_index):
                    self.assertTrue(
                        _route_avoids_box(route, box, pad=2.0),
                        "辺(%s)が無関係な箱%dを横切っている" % (route.label, index),
                    )
                self.assertFalse(
                    _rects_overlap(_label_rect(route), _box_rect(box)),
                    "ラベル(%s)が箱%dと重なっている" % (route.label, index),
                )
        a1a = next(route for route in layout.routes if route.label == "A1a")
        a1b = next(route for route in layout.routes if route.label == "A1b")
        self.assertNotEqual(
            a1a.points[-1], a1b.points[-1],
            "同じ結論へ入る2本の矢じりを同じ位置に重ねてはいけない",
        )


def _label_rect_with_halo(route, halo: float = 2.5):
    """描画どおりのラベル矩形（12px文字＋縁取り stroke-width 5 の半分を四方に足す）。"""
    rect = _label_rect(route)
    if rect is None:
        return None
    x, y, w, h = rect
    return (x - halo, y - halo, w + 2 * halo, h + 2 * halo)


class TestWrappedLayerLeftDetourLabel(unittest.TestCase):
    """2026-09-25 の撮影で見つかった崩れの再現。

    3つの起点（本文が長い）が同じ1つの箱へ矢印を出し、その先にもう1つ箱がある図を
    max_width=720 で組むと、層0が720pxに収まらず2段に折り返される。このとき左端の
    箱から出る辺が図の左外側を回り、そのラベルの x が viewBox の外（負）になって
    「来事ごと」と左が切れていた（右側の迂回ラベルは切れなかった）。
    """

    NODES = [
        {"id": "cc", "title": "Claude Code", "text": ".claude/settings.json（Git で管理）", "icon": "gear"},
        {"id": "cx", "title": "Codex", "text": ".codex/hooks.json（Git の対象外）", "icon": "gear"},
        {"id": "hm", "title": "Hermes", "text": "利用者フォルダの config.yaml", "icon": "gear"},
        {"id": "core", "title": "共通の台本", "text": "composer と部品", "icon": "document"},
        {"id": "rec", "title": "記録と頁", "text": "explain-page", "icon": "box"},
    ]
    EDGES = [
        {"from": "cc", "to": "core", "label": "出来事ごと"},
        {"from": "cx", "to": "core", "label": "出来事ごと"},
        {"from": "hm", "to": "core", "label": "出来事ごと"},
        {"from": "core", "to": "rec", "label": "指示と検品"},
    ]

    def setUp(self) -> None:
        self.layout = layout_diagram(self.NODES, self.EDGES, max_width=720)

    def test_precondition_layer0_is_wrapped_and_one_detour_goes_left(self) -> None:
        # 前提が崩れたらこの再現は何も確かめていないことになる＝前提そのものを固定する。
        sources = self.layout.boxes[:3]
        self.assertGreater(len({round(b.y) for b in sources}), 1, "層0が2段に折れていない")
        leftmost_box_x = min(b.x for b in self.layout.boxes)
        self.assertTrue(
            any(min(x for x, _ in r.points) < leftmost_box_x for r in self.layout.routes),
            "左外側を回る辺が無い（再現の前提が崩れた）",
        )

    def test_every_label_rect_is_inside_the_viewbox(self) -> None:
        for route in self.layout.routes:
            x, y, w, h = _label_rect_with_halo(route)
            self.assertGreaterEqual(x, 0.0, "ラベル(%s)が図の左の外へ出ている" % route.label)
            self.assertLessEqual(x + w, self.layout.width, "ラベル(%s)が図の右の外へ出ている" % route.label)
            self.assertGreaterEqual(y, 0.0, "ラベル(%s)が図の上の外へ出ている" % route.label)
            self.assertLessEqual(y + h, self.layout.height, "ラベル(%s)が図の下の外へ出ている" % route.label)

    def test_routes_and_boxes_stay_inside_the_viewbox(self) -> None:
        for box in self.layout.boxes:
            self.assertGreaterEqual(box.x, 0.0)
            self.assertLessEqual(box.x + box.w, self.layout.width)
        for route in self.layout.routes:
            for px, py in _route_path_points(route):
                self.assertGreaterEqual(px, 0.0, "辺(%s)が図の左の外を通る" % route.label)
                self.assertLessEqual(px, self.layout.width, "辺(%s)が図の右の外を通る" % route.label)

    def test_width_stays_within_max_width(self) -> None:
        self.assertLessEqual(self.layout.width, 720.0)

    def test_left_detour_label_does_not_touch_boxes_and_routes_avoid_boxes(self) -> None:
        for route in self.layout.routes:
            for index, box in enumerate(self.layout.boxes):
                self.assertFalse(
                    _rects_overlap(_label_rect(route), _box_rect(box)),
                    "ラベル(%s)が箱%dと重なっている" % (route.label, index),
                )
                if index not in (route.from_index, route.to_index):
                    self.assertTrue(
                        _route_avoids_box(route, box, pad=2.0),
                        "辺(%s)が無関係な箱%dを横切っている" % (route.label, index),
                    )


class TestSingleRowBackEdgesGoUnderTheRow(unittest.TestCase):
    """2026-09-25 の撮影で見つかった崩れの再現（公開用の見本の図）。

    3つの箱が1行（LR）に並ぶ鎖に戻る辺が2本ある図で、戻る辺が箱と同じ高さの一直線に
    なって自分の出発・到着の箱の中を横に突っ切り、ラベルが箱の見出しに重なった
    （「本棚の画面」が「本棚の画像を返す」に見えた）。いまは行の下を U 字に回る。
    """

    NODES = [
        {"id": "view", "title": "本棚の画面", "text": "表紙を表示したい"},
        {"id": "cache", "title": "ディスクキャッシュ", "text": "保存済みか確かめる"},
        {"id": "network", "title": "画像サーバー", "text": "無い時に取りに行く"},
    ]
    EDGES = [
        {"from": "view", "to": "cache", "label": "問い合わせ"},
        {"from": "cache", "to": "network", "label": "無い時だけ"},
        {"from": "network", "to": "cache", "label": "保存"},
        {"from": "cache", "to": "view", "label": "画像を返す"},
    ]

    def setUp(self) -> None:
        self.layout = layout_diagram(self.NODES, self.EDGES, max_width=720)
        self.back_routes = [r for r in self.layout.routes if r.label in ("保存", "画像を返す")]

    def test_precondition_is_a_single_row(self) -> None:
        self.assertEqual(self.layout.orientation, "LR")
        self.assertEqual(len({round(b.y) for b in self.layout.boxes}), 1)
        self.assertLessEqual(self.layout.width, 720.0)

    def test_back_edges_do_not_cut_through_any_box(self) -> None:
        for route in self.back_routes:
            for index, box in enumerate(self.layout.boxes):
                if index in (route.from_index, route.to_index):
                    # 自分の出発・到着の箱は縁に触れてよいが、中を通ってはいけない
                    inner = type("R", (), {"x": box.x + 1, "y": box.y + 1, "w": box.w - 2, "h": box.h - 2})
                    self.assertTrue(
                        _route_avoids_box(route, inner),
                        "戻る辺(%s)が自分の箱%dの中を通っている" % (route.label, index),
                    )
                else:
                    self.assertTrue(
                        _route_avoids_box(route, box, pad=2.0),
                        "戻る辺(%s)が無関係な箱%dを横切っている" % (route.label, index),
                    )

    def test_back_edges_run_below_the_row(self) -> None:
        row_bottom = max(b.y + b.h for b in self.layout.boxes)
        for route in self.back_routes:
            lane_ys = [y for _, y in route.points[1:-1]]
            self.assertTrue(lane_ys and all(y > row_bottom for y in lane_ys), route.label)

    def test_labels_do_not_overlap_boxes_and_stay_inside(self) -> None:
        for route in self.layout.routes:
            for index, box in enumerate(self.layout.boxes):
                self.assertFalse(
                    _rects_overlap(_label_rect(route), _box_rect(box)),
                    "ラベル(%s)が箱%dと重なっている" % (route.label, index),
                )
            x, y, w, h = _label_rect_with_halo(route)
            self.assertGreaterEqual(x, 0.0)
            self.assertLessEqual(x + w, self.layout.width)
            self.assertGreaterEqual(y, 0.0)
            self.assertLessEqual(y + h, self.layout.height)

    def test_routes_do_not_share_a_segment(self) -> None:
        routes = self.layout.routes
        for i, a in enumerate(routes):
            for b in routes[i + 1:]:
                for a1, a2 in zip(a.points, a.points[1:]):
                    for b1, b2 in zip(b.points, b.points[1:]):
                        self.assertFalse(
                            _segments_overlap_collinear(a1, a2, b1, b2),
                            "辺(%s)と辺(%s)が同じ線を通っている" % (a.label, b.label),
                        )


def _rendered_text_width(line: str, px: float) -> float:
    """描かれる文字の幅の、実測に合わせた見積もり（2026-09-26・Chromium の getBBox で実測）。

    全角＝1em（13pxの本文で1字13.0px・14pxの題で14.0px）、英大文字≒0.67em、それ以外の英数は
    実測（小文字≒0.47em）より大きめの 0.55em。本体の private 関数には頼らない。
    """
    width = 0.0
    for ch in line:
        if not ch.isascii():
            width += 1.0
        elif ch.isupper():
            width += 0.67
        else:
            width += 0.55
    return width * px


def _assert_text_inside_boxes(test: unittest.TestCase, layout) -> None:
    """描く側（題14px・本文13px・注記12px・左の余白14px・記号22px）で、どの行も箱の右の縁の内側。"""
    for index, box in enumerate(layout.boxes):
        indent = 14.0 + (22.0 if box.icon else 0.0)
        num_indent = (_rendered_text_width(box.num, 15.0) + 8.0) if box.num else 0.0
        for line_no, line in enumerate(box.title_lines):
            extra = num_indent if line_no == 0 else 0.0
            test.assertLessEqual(
                indent + extra + _rendered_text_width(line, 14.0), box.w + 0.5,
                "箱%dの題の行「%s」が右の縁を越える（箱の幅 %.1f）" % (index, line, box.w),
            )
        for line in box.body_lines:
            test.assertLessEqual(
                indent + _rendered_text_width(line, 13.0), box.w + 0.5,
                "箱%dの本文の行「%s」が右の縁を越える（箱の幅 %.1f）" % (index, line, box.w),
            )
        for line in box.note_lines:
            test.assertLessEqual(
                indent + _rendered_text_width(line, 12.0), box.w + 0.5,
                "箱%dの注記の行「%s」が右の縁を越える（箱の幅 %.1f）" % (index, line, box.w),
            )


class TestJapaneseBodyFitsInsideTheBox(unittest.TestCase):
    """2026-09-26 の撮影と実測で見つかった崩れの再現。

    箱の中の日本語の本文が右の縁を越えた。原因＝①全角1字を0.95emと見積もった（実寸は1em）
    ②本文を12.3pxで見積もり13pxで描いた ③層の箱の幅を上限260pxで切っても、字数で折った
    行（22字＝約286px）がその幅に入らない ④記号の分を19.6pxと見積もり22pxずらして描いた。
    実測＝日本語の本文で実寸÷見積もり＝1.10〜1.11、はみ出しは最大38.5px。
    """

    def test_the_reported_boxes_fit(self) -> None:
        nodes = [
            {"id": "cache", "title": "ディスクキャッシュ", "text": "URLのハッシュで保存済みか見る"},
            {"id": "server", "title": "画像サーバー", "text": "無ければここへ取りに行く"},
        ]
        edges = [{"from": "cache", "to": "server", "label": "無い時だけ"}]
        layout = layout_diagram(nodes, edges, max_width=720)
        _assert_text_inside_boxes(self, layout)

    def test_a_long_line_in_a_capped_box_is_rewrapped_to_fit(self) -> None:
        nodes = [
            {"id": "a", "title": "長い本文の箱", "text": "画像サーバーから取れたら保存して次回の表示に使う"},
            {"id": "b", "title": "次の箱", "text": "短い本文"},
        ]
        layout = layout_diagram(nodes, [{"from": "a", "to": "b"}], max_width=720)
        self.assertLessEqual(max(b.w for b in layout.boxes), 260.0)
        self.assertGreaterEqual(len(layout.boxes[0].body_lines), 2, "上限の幅に入るよう折り直していない")
        _assert_text_inside_boxes(self, layout)

    def test_an_icon_box_leaves_room_for_the_icon(self) -> None:
        nodes = [
            {"id": "a", "title": "記号つきの箱", "text": "記号の分だけ本文が右へずれる", "icon": "gear"},
            {"id": "b", "title": "英数の箱", "text": "cache hit ratio 0.93 via SHA256"},
        ]
        layout = layout_diagram(nodes, [{"from": "a", "to": "b"}], max_width=720)
        _assert_text_inside_boxes(self, layout)

    def test_a_fan_out_with_detours_on_both_sides_stays_within_720(self) -> None:
        # 実際の頁で 722px になった図と同じ形・同じ字数（見出し7〜8字・本文10〜14字・記号と番号つき・
        # 中央の段が3つ・両側を回る迂回線）。箱を広く見積もったぶん迂回線が外へ出た。
        nodes = [
            {"id": "a", "num": "1", "title": "準備の段取りを", "text": "最初に全体の流れを確かめる", "icon": "clock"},
            {"id": "b", "num": "2", "title": "読む前の整理の段", "text": "材料を三つの山に分けて置く", "icon": "scales"},
            {"id": "c", "num": "3", "title": "時事の確認の段", "text": "新しい話題を先に拾って", "icon": "news"},
            {"id": "d", "num": "4", "title": "知識の点検の段", "text": "覚えた事を順に見直す", "icon": "school"},
            {"id": "e", "num": "5", "title": "翌日の配分の段", "text": "残りの時間を苦手な所へ回そう", "icon": "flag"},
        ]
        edges = [
            {"from": "a", "to": "b", "label": "12点満点で見る"},
            {"from": "a", "to": "c", "label": "6点満点で見る"},
            {"from": "a", "to": "d", "label": "20点満点で見る"},
            {"from": "b", "to": "e", "label": "5点以下なら80分"},
            {"from": "c", "to": "e", "label": "2点以下なら70分"},
            {"from": "d", "to": "e", "label": "8点以下なら40分"},
        ]
        layout = layout_diagram(nodes, edges, max_width=720)
        self.assertLessEqual(layout.width, 720.0)
        # 組み直したあとも、同じ段（b・c・d）の箱は同じ幅にそろっている（並べた箱を返している）
        self.assertEqual(len({round(layout.boxes[i].w, 3) for i in (1, 2, 3)}), 1)
        _assert_text_inside_boxes(self, layout)


class TestExplicitPlacementLeftDetourLabel(unittest.TestCase):
    """位置（col/row）を指定した図＝旧経路でも、左の外周を回る辺の長いラベルが
    図の左の外へ出ていた（2026-09-25 実測＝見積りの左端が -23px）。"""

    def test_long_label_on_left_perimeter_is_inside_the_viewbox(self) -> None:
        nodes = [
            {"id": "P1", "title": "対象範囲・予定枠・期待効果・運用体制", "col": 0, "row": 0},
            {"id": "V1", "title": "全ての利用者の機会を公平に確保", "col": 1, "row": 0},
            {"id": "Q1", "title": "人材不足・効果未検証・現場負担", "col": 0, "row": 1},
            {"id": "Q2", "title": "人材不足・効果未検証・公平な機会", "col": 1, "row": 1},
            {"id": "R1", "title": "週10時間の全店実施を当面維持", "col": 0, "row": 2},
            {"id": "R2", "title": "継続的に評価して見直す", "col": 1, "row": 2},
        ]
        edges = [
            {"from": "P1", "to": "R1", "label": "出来事ごと"},
            {"from": "Q1", "to": "R1", "label": "A2"},
            {"from": "Q2", "to": "R2", "label": "A3"},
        ]
        layout = layout_diagram(nodes, edges, max_width=720)
        leftmost_box_x = min(b.x for b in layout.boxes)
        self.assertTrue(
            any(min(x for x, _ in r.points) < leftmost_box_x for r in layout.routes),
            "左外側を回る辺が無い（再現の前提が崩れた）",
        )
        for route in layout.routes:
            x, _, w, _ = _label_rect_with_halo(route)
            self.assertGreaterEqual(x, 0.0, "ラベル(%s)が図の左の外へ出ている" % route.label)
            self.assertLessEqual(x + w, layout.width, "ラベル(%s)が図の右の外へ出ている" % route.label)


if __name__ == "__main__":
    unittest.main()
