# -*- coding: utf-8 -*-
"""数学题示意图生成器 v2（精确优先）。

原则：只对能从题干可靠解析出图形参数的题配图，解析不出就返回 None（不画，
避免误导）。图形风格为干净的黑白线条图（仿教辅）。

支持：
1. 数轴：题干/括注给出每个字母点的显式位置（a=-3、a 在 -2 和 -1 之间、
   原点左/右侧并按 |a|>|b| 之类排序修正）时精确绘制。
2. 函数/坐标系：题干给出明确解析式（一次/正比例/反比例/二次函数且括注给出
   开口与 x 轴交点等）时按式与括注精确绘制。
3. 平面几何：直角三角形（带直角符号）等可确定形状的基础图形；可标注题干
   明确给出的边长与角度文字。条件不足不画。
"""
import html
import re

_W, _H = 320, 200


def _esc(s):
    return html.escape(str(s or ""), quote=True)


def _svg(body, w=_W, h=_H):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
        'width="%d" height="%d" font-family="Georgia, \'Times New Roman\', serif" '
        'role="img">%s</svg>' % (w, h, w, h, body)
    )


# ============================================================
# 1. 数轴（精确）
# ============================================================
def _number_line(content):
    if "数轴" not in content and "原点" not in content:
        return None
    # 显式值：a=-3（前后不能是字母，避免把 AB=5 误读成 b=5）
    pts = {}
    for m in re.finditer(r"(?<![A-Za-z0-9])([a-z])\s*=\s*(-?\d+(?:\.\d+)?)(?![\d.])", content.lower()):
        pts.setdefault(m.group(1), float(m.group(2)))
    # 区间：a 在 m 和 n 之间 / a 在 -2 和 -1 之间
    for m in re.finditer(r"(?<![A-Za-z0-9])([a-z])\s*在\s*(-?\d+(?:\.\d+)?)\s*和\s*(-?\d+(?:\.\d+)?)\s*之间", content.lower()):
        lo, hi = float(m.group(2)), float(m.group(3))
        pts.setdefault(m.group(1), (lo + hi) / 2.0)
    # 原点左/右（默认 ±1.6，随后按 |a|>|b| 修正距离）
    for m in re.finditer(r"(?<![A-Za-z0-9])([a-z])\s*在\s*原点(左侧|右侧)", content.lower()):
        pts.setdefault(m.group(1), -1.6 if m.group(2) == "左侧" else 1.6)

    if not pts:
        return None
    # |a|>|b|（或反之）：把同边两点按绝对值拉开，保证图与条件一致
    m = re.search(r"\|\s*([a-z])\s*\|\s*([<>])\s*\|\s*([a-z])\s*\|", content.lower())
    if m:
        big, rel, small = m.group(1), m.group(2), m.group(3)
        if rel == ">":
            b_abs, s_abs = 2.4, 1.3
        else:
            b_abs, s_abs = 1.3, 2.4
        if big in pts and pts[big] == 1.6:
            pts[big] = b_abs if pts[big] > 0 else -b_abs
        if small in pts and pts[small] == 1.6:
            pts[small] = s_abs if pts[small] > 0 else -s_abs

    if not pts:
        return None
    vals = [pts[k] for k in pts]
    if any(v < -20 or v > 20 for v in vals):
        return None
    lo = min([-3] + [v - 0.9 for v in vals])
    hi = max([3] + [v + 0.9 for v in vals])
    span = hi - lo
    if span > 12:
        lo, hi = -5, 5

    w, h = 340, 92
    x0, x1 = 26, w - 26
    y = 46

    def px(xv):
        return x0 + (xv - lo) / (hi - lo) * (x1 - x0)

    body = [
        f'<line x1="{x0-12}" y1="{y}" x2="{x1}" y2="{y}" stroke="#111" stroke-width="1.5"/>',
        f'<path d="M{x1+4} {y} l-9 -5 m9 5 l-9 5" stroke="#111" stroke-width="1.5" fill="none"/>',
    ]
    # 整数刻度（范围内尽量少而清）
    for k in range(int(lo) - 1, int(hi) + 2):
        if k < lo - 0.4 or k > hi + 0.4:
            continue
        xx = px(k)
        body.append(f'<line x1="{xx:.1f}" y1="{y-4}" x2="{xx:.1f}" y2="{y+4}" stroke="#111" stroke-width="1"/>')
        if k == 0:
            body.append(f'<text x="{xx:.1f}" y="{y+17}" text-anchor="middle" font-size="12" fill="#000">0</text>')
        elif abs(k) <= 8:
            body.append(f'<text x="{xx:.1f}" y="{y+17}" text-anchor="middle" font-size="10" fill="#333">{k}</text>')
    for ch in sorted(pts, key=lambda c: pts[c]):
        xx = px(pts[ch])
        body.append(f'<circle cx="{xx:.1f}" cy="{y}" r="4" fill="#fff" stroke="#000" stroke-width="1.6"/>')
        body.append(f'<text x="{xx:.1f}" y="{y-11}" text-anchor="middle" font-size="13" fill="#000" font-style="italic">{_esc(ch)}</text>')
    return _svg("".join(body), w=w, h=h)


# ============================================================
# 2. 坐标系与函数（需明确解析式 / 关键点）
# ============================================================
def _coord_plane(content):
    if not any(k in content for k in ("坐标", "图象", "图像", "函数", "双曲线", "抛物线", "一次函数", "反比例")):
        return None
    low = content.lower()

    def pt(xv, yv):
        return ox + xv * s, oy - yv * s

    # 收集括注关键信息（写在题干括号里的图形描述）
    note = ""
    for m in re.finditer(r"[（(]([^（）()]{2,60})[)）]", content):
        seg = m.group(1)
        if any(k in seg for k in ("开口", "对称轴", "交", "顶点", "过点", "图象过", "经过点", "与 x 轴", "与 y 轴")):
            note += seg + " "

    curves = []  # (kind, params)
    # 一次/正比例：y = kx 或 y = kx + b（k 可从括注/式提取）
    m = re.search(r"y\s*=\s*(-?\d+(?:\.\d+)?|[\u2212]\d+)\s*x\s*([+\-]\s*\d+)?", content)
    if m:
        k = float(m.group(1).replace("−", "-"))
        b = 0
        if m.group(2):
            bb = re.sub(r"\s", "", m.group(2))
            b = float(bb)
        curves.append(("line", k, b))
    # 反比例 y=k/x
    m = re.search(r"y\s*=\s*(-?\d+(?:\.\d+)?)\s*/\s*x", content)
    if m:
        k = float(m.group(1))
        curves.append(("hyper", k))
    # 二次函数 + 括注有 x 轴交点或对称轴时
    if ("二次" in low) or ("抛物线" in low) or ("ax²" in low):
        xs = [float(v) for v in re.findall(r"[（(]\s*(-?\d+)\s*,\s*0\s*[)）]", note + content)]
        down = "开口向下" in note or "开口朝下" in note
        if len(xs) >= 2:
            curves.append(("para_xs", sorted(xs)[0], sorted(xs)[1], -1 if down else 1))
        elif len(xs) == 1:
            # 只一个交点不画抛物线（信息不足）
            pass

    if not curves:
        # 没有任何可确定的曲线 → 不配图（避免误导）
        return None

    w, h = 340, 300
    ox, oy = 170, 150
    s = 26
    half_x = 5.2
    half_y = 5.2

    body = ['<g stroke="#ddd" stroke-width="1">']
    for i in range(-5, 6):
        body.append(f'<line x1="{ox+i*s}" y1="{oy-half_y*s}" x2="{ox+i*s}" y2="{oy+half_y*s}"/>')
        body.append(f'<line x1="{ox-half_x*s}" y1="{oy+i*s}" x2="{ox+half_x*s}" y2="{oy+i*s}"/>')
    body.append("</g>")
    body.append(f'<line x1="{ox-half_x*s}" y1="{oy}" x2="{ox+half_x*s}" y2="{oy}" stroke="#111" stroke-width="1.5"/>')
    body.append(f'<line x1="{ox}" y1="{oy+half_y*s}" x2="{ox}" y2="{oy-half_y*s}" stroke="#111" stroke-width="1.5"/>')
    body.append(f'<path d="M{ox+half_x*s+2} {oy} l-8 -4 m8 4 l-8 4" stroke="#111" stroke-width="1.4" fill="none"/>')
    body.append(f'<path d="M{ox} {oy-half_y*s-2} l-4 8 m4 -8 l4 8" stroke="#111" stroke-width="1.4" fill="none"/>')
    for i in range(-5, 6):
        if i == 0:
            continue
        if abs(i) <= 5:
            body.append(f'<text x="{ox+i*s}" y="{oy+16}" text-anchor="middle" font-size="10" fill="#333">{i}</text>')
            body.append(f'<text x="{ox-14}" y="{oy-i*s+4}" text-anchor="end" font-size="10" fill="#333">{i}</text>')
    body.append(f'<text x="{ox+half_x*s-2}" y="{oy-16}" text-anchor="middle" font-size="13" font-style="italic">x</text>')
    body.append(f'<text x="{ox+16}" y="{oy-half_y*s+8}" text-anchor="middle" font-size="13" font-style="italic">y</text>')
    body.append(f'<text x="{ox-14}" y="{oy+16}" text-anchor="middle" font-size="11">0</text>')

    for cur in curves:
        if cur[0] == "line":
            k, b = cur[1], cur[2]
            p1, p2 = pt(-4.5, k * -4.5 + b), pt(4.5, k * 4.5 + b)
            body.append(f'<line x1="{p1[0]:.1f}" y1="{p1[1]:.1f}" x2="{p2[0]:.1f}" y2="{p2[1]:.1f}" stroke="#000" stroke-width="2"/>')
        elif cur[0] == "hyper":
            k = cur[1]
            # y = k/x：k>0 → 一、三象限；k<0 → 二、四象限
            quadrants = [(1, 1), (-1, -1)] if k > 0 else [(-1, 1), (1, -1)]
            for (sx, sy) in quadrants:
                ptsv = []
                for i in range(1, 55):
                    xv = i / 8.0
                    yv = k / xv
                    if abs(yv) < 0.3 or abs(yv) > 5.2:
                        continue
                    xp, yp = pt(sx * xv, sy * yv)
                    ptsv.append("%.1f,%.1f" % (xp, yp))
                if ptsv:
                    body.append('<path d="M ' + " L ".join(ptsv) + '" fill="none" stroke="#000" stroke-width="2"/>')
        elif cur[0] == "para_xs":
            x1, x2, a = cur[1], cur[2], cur[3]
            # 顶点 x = (x1+x2)/2；a<0 向下。选择高度使顶点 y 取 2.2（美观）
            vx = (x1 + x2) / 2
            # f(x) = a(x-x1)(x-x2) → 用 A = a_scale * 使在顶点达 ~2.4
            # 顶点 |y| = |a_scale|*(vx-x1)(vx-x2) ; (vx-x1)=(vx-x2)=d → y= -a*d^2
            d = abs(vx - x1)
            target = 2.4
            a_scale = target / (d * d) if d else 0
            a_scale = a_scale * (-1 if a < 0 else 1)
            ptsv = []
            for i in range(-120, 121):
                xv = vx + (x1 - 4) + (i + 120) / 240.0 * ((x2 + 4) - (x1 - 4))
                # clamp
                xv = max(x1 - 3, min(x2 + 3, xv))
                yv = a_scale * (xv - x1) * (xv - x2)
                if yv < -5.4 or yv > 5.4:
                    continue
                ptsv.append(f"{pt(xv, yv)[0]:.1f},{pt(xv, yv)[1]:.1f}")
            if ptsv:
                body.append('<path d="M ' + " L ".join(ptsv) + f'" fill="none" stroke="#000" stroke-width="2.1"/>')
            for x0v in (x1, x2):
                xp, yp = pt(x0v, 0)
                body.append(f'<circle cx="{xp:.1f}" cy="{yp:.1f}" r="3.4" fill="#fff" stroke="#000" stroke-width="1.5"/>')
    return _svg("".join(body), w=w, h=h)


# ============================================================
# 3. 平面几何（保守）
# ============================================================
def _geometry(content):
    text = content
    # 直角三角形：Rt△ABC 或 △ABC 中…90° / ∠A=90° → 画标准直角三角
    m = re.search(r"Rt\s*△?\s*([A-Z]{3})", text) or re.search(r"△\s*([A-Z]{3})", text)
    is_right = ("Rt" in text) or re.search(r"∠\s*([A-Z])\s*=\s*90\s*°", text) or ("直角" in text and "△" in text)
    if m and is_right:
        verts = m.group(1).upper()
        # 直角顶点：括号里给出，或默认第一个字母对应直角放在左下
        ang = None
        ma = re.search(r"∠\s*([A-Z])\s*=\s*90\s*°", text)
        if ma:
            ang = ma.group(1).upper()
        if not ang:
            ang = verts[0] if verts[0] not in ("A",) else "A"
        # 布局：把直角顶点放左下，另两顶点 A(?) 右上/右下
        # 简单三角 A(左下直角), B(右下), C(上中) 若 ang=A 才对应；否则按顺序排
        left = ang
        others = [c for c in verts if c != ang][:2]
        p_right = (250, 150)
        p_top = (90, 70)
        p_left = (90, 150)
        # 把其余两点放 right / top
        lab_pos = {left: p_left, others[0]: p_right, others[1]: p_top}
        body = []
        for v, (x, y) in lab_pos.items():
            body.append(f'<circle cx="{x}" cy="{y}" r="3" fill="#000"/>')
        # 三角形
        body.append(f'<polygon points="{p_left[0]},{p_left[1]} {p_right[0]},{p_right[1]} {p_top[0]},{p_top[1]}" fill="#fff" stroke="#000" stroke-width="1.8"/>')
        # 直角符
        body.append('<path d="M 102 150 L 102 138 L 90 138" fill="none" stroke="#000" stroke-width="1.4"/>')
        # 标签
        for v, (x, y) in lab_pos.items():
            dx = 0 if x == 90 else 12
            dy = -8 if y == 70 else 20
            body.append(f'<text x="{x+dx}" y="{y+dy}" text-anchor="middle" font-size="14" font-style="italic" fill="#000">{_esc(v)}</text>')
        # 题干给的边长/角度标注（文本贴图，按文字位置示意放置到边中点）
        # 边长 AB=xx
        for mm in re.finditer(r"\b(AB|BC|AC)\s*=\s*(\d+(?:\.\d+)?)", text):
            a1, a2 = mm.group(1)[0], mm.group(1)[1]
            if a1 in lab_pos and a2 in lab_pos:
                (x1, y1), (x2, y2) = lab_pos[a1], lab_pos[a2]
                mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                body.append(f'<text x="{mx:.0f}" y="{my:.0f}" text-anchor="middle" font-size="12" fill="#000">{_esc(mm.group(1))}={_esc(mm.group(2))}</text>')
        for mm in re.finditer(r"∠\s*([A-Z])\s*=\s*(\d+)\s*°", text):
            v = mm.group(1).upper()
            if v in lab_pos:
                x, y = lab_pos[v]
                body.append(f'<text x="{x+16}" y="{y+6}" text-anchor="start" font-size="12" fill="#000">{_esc(v)} = {mm.group(2)}°</text>')
        return _svg("".join(body), w=340, h=200)
    return None


# ============================================================
# 主入口
# ============================================================
def generate_math_image(content):
    if not content:
        return None
    for fn in (_number_line, _coord_plane, _geometry):
        try:
            svg = fn(content)
        except Exception:
            svg = None
        if svg:
            return svg
    return None
