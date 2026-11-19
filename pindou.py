#!/usr/bin/env python3
"""将图片转换为 MARD 色卡拼豆图纸。"""

import argparse
from collections import Counter
import csv
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from ciede2000_reference import REFERENCE_DATA


BASE_DIR = Path(__file__).resolve().parent


def load_palette(path):
    """读取并检查色卡，保留文件中的顺序以处理等距颜色。"""
    with open(path, encoding="utf-8") as source:
        data = json.load(source)
    colors = data.get("colors")
    if not isinstance(colors, list) or not colors:
        raise ValueError("色卡必须包含非空的 colors 列表")
    seen = set()
    for item in colors:
        if not isinstance(item, dict) or not isinstance(item.get("code"), str) or not item["code"].strip():
            raise ValueError("色卡存在无效色号")
        if item["code"] in seen:
            raise ValueError("色卡存在重复色号：{}".format(item["code"]))
        seen.add(item["code"])
        if not isinstance(item.get("hex"), str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", item["hex"]):
            raise ValueError("色号 {} 的 HEX 格式无效".format(item["code"]))
    return colors


def normalize_code(value):
    """把 A06、c6 这类写法归一成色卡里的 A6、C6，去掉字母后数字的前导零。"""
    match = re.fullmatch(r"([A-Za-z]+)0*(\d+)", value)
    if not match:
        return value.upper()
    return "{}{}".format(match.group(1).upper(), match.group(2).lstrip("0") or "0")


def load_color_pool(spec, palette):
    """解析颜色池并按 HEX 去重，保留首次出现时的顺序和色号。"""
    path = Path(spec[1:] if spec.startswith("@") else spec)
    if spec.startswith("@") or ("," not in spec and (path.is_file() or path.suffix.lower() == ".json")):
        with open(path, encoding="utf-8-sig") as source:
            content = source.read()
        if path.suffix.lower() == ".json" or content.lstrip().startswith("["):
            values = json.loads(content)
            if not isinstance(values, list):
                raise ValueError("颜色池 JSON 必须是数组")
        else:
            values = []
            for line in content.splitlines():
                value = line.strip()
                if value and (not value.startswith("#") or re.fullmatch(r"#[0-9a-fA-F]{6}", value)):
                    values.append(value)
    else:
        values = spec.split(",") if spec.strip() else []
    lookup = {item["code"].upper(): item for item in palette}
    colors, seen = [], set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("颜色池包含空值或非字符串值")
        value = value.strip()
        if re.fullmatch(r"#?[0-9a-fA-F]{6}", value):
            hex_value = "#" + value.lstrip("#").upper()
            code = "-"
        else:
            item = lookup.get(value.upper())
            if item is None:
                item = lookup.get(normalize_code(value))
            if item is None:
                raise ValueError("颜色池中的 MARD 色号不存在或 HEX 格式无效：{}".format(value))
            hex_value = item["hex"].upper()
            code = item["code"]
        if hex_value not in seen:
            seen.add(hex_value)
            colors.append({"code": str(len(colors) + 1), "mard_code": code, "hex": hex_value,
                           "label": str(len(colors) + 1)})
    if not colors:
        raise ValueError("颜色池不能为空")
    if len(colors) > 221:
        raise ValueError("颜色池去重后不能超过 221 色")
    return colors


def rgb_to_lab(rgb):
    """sRGB（D65）转 CIELAB；输入最后一维为 0–255 RGB。"""
    rgb = np.asarray(rgb, dtype=np.float64) / 255.0
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    matrix = np.array([[0.4124564, 0.3575761, 0.1804375],
                       [0.2126729, 0.7151522, 0.0721750],
                       [0.0193339, 0.1191920, 0.9503041]])
    # 显式逐通道求和，避免部分系统 BLAS 对小矩阵产生浮点警告。
    xyz = np.sum(linear[..., None, :] * matrix, axis=-1) / np.array([0.95047, 1.0, 1.08883])
    delta = 6.0 / 29.0
    f = np.where(xyz > delta ** 3, np.cbrt(xyz), xyz / (3 * delta ** 2) + 4.0 / 29.0)
    return np.stack((116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]),
                     200 * (f[..., 1] - f[..., 2])), axis=-1)


def ciede2000(lab1, lab2):
    """计算 CIEDE2000 色差，支持 NumPy 广播；权重均为 1。"""
    l1, a1, b1 = np.moveaxis(np.asarray(lab1, dtype=np.float64), -1, 0)
    l2, a2, b2 = np.moveaxis(np.asarray(lab2, dtype=np.float64), -1, 0)
    c1 = np.hypot(a1, b1)
    c2 = np.hypot(a2, b2)
    cbar = (c1 + c2) / 2
    g = 0.5 * (1 - np.sqrt(cbar ** 7 / (cbar ** 7 + 25.0 ** 7)))
    ap1, ap2 = (1 + g) * a1, (1 + g) * a2
    cp1, cp2 = np.hypot(ap1, b1), np.hypot(ap2, b2)
    hp1 = np.mod(np.degrees(np.arctan2(b1, ap1)), 360)
    hp2 = np.mod(np.degrees(np.arctan2(b2, ap2)), 360)
    dl = l2 - l1
    dc = cp2 - cp1
    dh = hp2 - hp1
    dh = np.where(cp1 * cp2 == 0, 0, np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh)))
    d_h = 2 * np.sqrt(cp1 * cp2) * np.sin(np.radians(dh / 2))
    lbar = (l1 + l2) / 2
    cpbar = (cp1 + cp2) / 2
    hsum = hp1 + hp2
    hbar = np.where(cp1 * cp2 == 0, hsum,
                    np.where(np.abs(hp1 - hp2) <= 180, hsum / 2,
                             np.where(hsum < 360, (hsum + 360) / 2, (hsum - 360) / 2)))
    t = (1 - 0.17 * np.cos(np.radians(hbar - 30)) + 0.24 * np.cos(np.radians(2 * hbar))
         + 0.32 * np.cos(np.radians(3 * hbar + 6)) - 0.20 * np.cos(np.radians(4 * hbar - 63)))
    sl = 1 + 0.015 * (lbar - 50) ** 2 / np.sqrt(20 + (lbar - 50) ** 2)
    sc = 1 + 0.045 * cpbar
    sh = 1 + 0.015 * cpbar * t
    rt = (-2 * np.sqrt(cpbar ** 7 / (cpbar ** 7 + 25.0 ** 7))
          * np.sin(np.radians(60 * np.exp(-((hbar - 275) / 25) ** 2))))
    x, y, z = dl / sl, dc / sc, d_h / sh
    return np.sqrt(x * x + y * y + z * z + rt * y * z)


def self_check():
    """使用论文补充材料中的全部 34 组数据校验实现。"""
    for index, (lab1, lab2, expected) in enumerate(REFERENCE_DATA, 1):
        actual = float(ciede2000(lab1, lab2))
        if not np.isfinite(actual) or abs(actual - expected) > 0.00005:
            raise ValueError("CIEDE2000 自检失败：第 {} 组，实际 {:.6f}，参考 {:.4f}".format(index, actual, expected))


def kmeans_indices(image, palette_lab, k, iterations=40, seed=0):
    """Lab 空间加权 k-means 聚类，每个聚类中心取成员的 RGB 加权均值，再映射到色卡。"""
    arr = np.asarray(image, dtype=np.uint8)
    pixels = arr.reshape(-1, 3)
    unique, inverse, counts = np.unique(pixels, axis=0, return_inverse=True, return_counts=True)
    unique_labs = rgb_to_lab(unique)
    weights = counts.astype(np.float64)
    rng = np.random.default_rng(seed)
    # k-means++ 初始化，按像素频次加权
    prob = weights / weights.sum()
    centers = [unique_labs[int(rng.choice(len(unique_labs), p=prob))]]
    for _ in range(k - 1):
        d = np.min(np.stack([np.sum((unique_labs - c) ** 2, axis=1) for c in centers], axis=0), axis=0)
        score = d * weights
        total = score.sum()
        if total <= 0:
            break
        centers.append(unique_labs[int(rng.choice(len(unique_labs), p=score / total))])
    centers = np.asarray(centers, dtype=np.float64)
    labels = np.full(len(unique_labs), -1, dtype=np.int64)
    for it in range(iterations):
        d = ((unique_labs[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        new_labels = np.argmin(d, axis=1)
        if it > 0 and np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for j in range(len(centers)):
            mask = labels == j
            if mask.any():
                w = weights[mask][:, None]
                centers[j] = (unique_labs[mask] * w).sum(axis=0) / w.sum()
    # 用成员的 RGB 加权均值作为该簇代表色
    reps = np.zeros((len(centers), 3), dtype=np.float64)
    for j in range(len(centers)):
        mask = labels == j
        if mask.any():
            w = weights[mask][:, None]
            reps[j] = (unique[mask].astype(np.float64) * w).sum(axis=0) / w.sum()
    rep_palette = nearest_color(np.clip(np.rint(reps), 0, 255).astype(np.uint8), palette_lab)
    per_unique = rep_palette[labels]
    return per_unique[inverse].reshape(arr.shape[:2])


def prune_colors(indices, palette_lab, max_colors):
    """保留用量最多的 max_colors 种色卡色，其余像素重新映射到这些保留色。"""
    counts = Counter(indices.flat)
    keep = [idx for idx, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:max_colors]]
    if len(keep) == len(counts):
        return indices
    keep_sorted = sorted(keep)
    keep_labs = palette_lab[keep_sorted]
    lookup = {}
    for idx in counts:
        if idx in lookup:
            continue
        if idx in keep:
            lookup[idx] = idx
        else:
            distances = ciede2000(palette_lab[idx][None, :], keep_labs)[0]
            lookup[idx] = keep_sorted[int(np.argmin(distances))]
    mapping = np.arange(len(palette_lab))
    for src, dst in lookup.items():
        mapping[src] = dst
    return mapping[indices]


def nearest_color(rgb, palette_lab):
    """为输入 RGB 寻找最近色卡索引，返回的形状与像素网格一致。"""
    pixels = np.asarray(rgb, dtype=np.uint8)
    unique, inverse = np.unique(pixels.reshape(-1, 3), axis=0, return_inverse=True)
    labs = rgb_to_lab(unique)
    indices = []
    # 分块限制临时色差矩阵的内存占用。
    for start in range(0, len(labs), 256):
        distances = ciede2000(labs[start:start + 256, None, :], palette_lab[None, :, :])
        indices.extend(np.argmin(distances, axis=1))
    return np.asarray(indices)[inverse].reshape(pixels.shape[:-1])


def prepare_image(path, width, height, method=Image.Resampling.LANCZOS):
    """按目标比例居中裁剪并缩放到网格尺寸。"""
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        return ImageOps.fit(image, (width, height), method=method, centering=(0.5, 0.5))


def fit_box(source_width, source_height, width, height):
    """计算与 ImageOps.fit 一致的居中浮点裁剪框。"""
    ratio = width / height
    if source_width / source_height == ratio:
        crop_width, crop_height = source_width, source_height
    elif source_width / source_height >= ratio:
        crop_width, crop_height = ratio * source_height, source_height
    else:
        crop_width, crop_height = source_width, source_width / ratio
    left = (source_width - crop_width) * 0.5
    top = (source_height - crop_height) * 0.5
    return left, top, left + crop_width, top + crop_height


def axis_weights(start, end, cells):
    """返回源像素、目标格及覆盖宽度；兼容缩小和放大。"""
    edges = np.linspace(start, end, cells + 1)
    first = np.floor(edges[:-1]).astype(np.int64)
    last = np.ceil(edges[1:]).astype(np.int64)
    counts = last - first
    cell = np.repeat(np.arange(cells), counts)
    pixel = np.repeat(first, counts) + np.arange(counts.sum()) - np.repeat(np.cumsum(counts) - counts, counts)
    overlap = np.minimum(pixel + 1, edges[cell + 1]) - np.maximum(pixel, edges[cell])
    valid = overlap > 0
    return pixel[valid], cell[valid], overlap[valid]


def area_samples(image, width, height):
    """展开裁剪区域内源像素与目标格的交叠及面积。"""
    arr = np.asarray(image, dtype=np.uint8)
    left, top, right, bottom = fit_box(arr.shape[1], arr.shape[0], width, height)
    xp, xc, xw = axis_weights(left, right, width)
    yp, yc, yw = axis_weights(top, bottom, height)
    pixels = arr[yp[:, None], xp[None, :]].reshape(-1, 3)
    cells = (yc[:, None] * width + xc[None, :]).ravel()
    weights = (yw[:, None] * xw[None, :]).ravel()
    return pixels, cells, weights, (xp, xc, yp, yc, left, top, right, bottom)


def area_resample(image, width, height, palette_lab, method):
    """按实际覆盖面积投票，返回色卡索引。"""
    pixels, cells, weights, geometry = area_samples(image, width, height)
    if method == "vote":
        labels = nearest_color(pixels, palette_lab)
        votes = np.zeros((height * width, len(palette_lab)), dtype=np.float32)
        left, top, right, bottom = geometry[4:]
        cell_area = (right - left) * (bottom - top) / (width * height)
        np.add.at(votes, (cells, labels), (weights / cell_area).astype(np.float32))
        return np.argmax(votes, axis=1).reshape(height, width)
    if method != "mode":
        raise ValueError("不支持的面积重采样模式：{}".format(method))
    # 同一格、同一 RGB 的面积合并；平票时选离格中心最近的源像素。
    rgb = pixels.astype(np.uint32)
    packed = (rgb[:, 0] << 16) | (rgb[:, 1] << 8) | rgb[:, 2]
    keys = cells.astype(np.int64) * (1 << 24) + packed
    xp, xc, yp, yc, left, top, right, bottom = geometry
    dx = xp + 0.5 - (left + (xc + 0.5) * (right - left) / width)
    dy = yp + 0.5 - (top + (yc + 0.5) * (bottom - top) / height)
    distance = (dy[:, None] ** 2 + dx[None, :] ** 2).ravel()
    order = np.argsort(keys, kind="stable")
    keys, weights, distance = keys[order], weights[order], distance[order]
    starts = np.r_[0, np.flatnonzero(keys[1:] != keys[:-1]) + 1]
    sums = np.add.reduceat(weights, starts)
    closest = np.minimum.reduceat(distance, starts)
    group_keys = keys[starts]
    group_cells = group_keys // (1 << 24)
    cell_starts = np.r_[0, np.flatnonzero(group_cells[1:] != group_cells[:-1]) + 1]
    maxima = np.maximum.reduceat(sums, cell_starts)
    tied = np.isclose(sums, maxima[group_cells], rtol=1e-12, atol=1e-12)
    candidate_distance = np.where(tied, closest, np.inf)
    best = np.minimum.reduceat(candidate_distance, cell_starts)
    winners = np.flatnonzero(tied & (candidate_distance == best[group_cells]))
    _, first = np.unique(group_cells[winners], return_index=True)
    chosen = (group_keys[winners[first]] % (1 << 24)).astype(np.uint32)
    result = np.stack((chosen >> 16, (chosen >> 8) & 255, chosen & 255), axis=-1).astype(np.uint8)
    return nearest_color(result.reshape(height, width, 3), palette_lab)


def relative_luminance(rgb):
    """计算 sRGB 的相对亮度，用于比较黑白文字的对比度。"""
    values = np.asarray(rgb, dtype=np.float64) / 255
    linear = np.where(values <= 0.04045, values / 12.92, ((values + 0.055) / 1.055) ** 2.4)
    return float(np.sum(linear * np.array([0.2126, 0.7152, 0.0722])))


def choose_font(size):
    # 优先使用常见的无衬线字体，Pillow 自带字体作为最后的回退。
    for name in ("DejaVuSans.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf",
                 "/Library/Fonts/Arial.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def choose_coordinate_font(size):
    """优先使用较窄的粗体数字，让小格子的多位坐标更清晰。"""
    for name in ("DejaVuSansCondensed-Bold.ttf",
                 "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf",
                 "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf",
                 "arialbd.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return choose_font(size)


def coordinate_tile(number, cell_size):
    """在独立图层中绘制坐标；必要时缩小字形，保证绝不越出格子。"""
    text = str(number)
    available = max(1, cell_size - 2)
    # 按实际数字测量宽高，优先使用能放进网格的最大字号。
    font = None
    for size in range(max(1, cell_size - 2), 0, -1):
        candidate = choose_coordinate_font(size)
        box = candidate.getbbox(text)
        font = candidate
        if box[2] - box[0] <= available and box[3] - box[1] <= available:
            break
    box = font.getbbox(text)
    glyph = Image.new("L", (max(1, box[2] - box[0]), max(1, box[3] - box[1])), 0)
    ImageDraw.Draw(glyph).text((-box[0], -box[1]), text, font=font, fill=255)
    # 极小格子或只有固定大小字体时，最终也必须约束在格内。
    if glyph.width > available or glyph.height > available:
        glyph.thumbnail((available, available), Image.Resampling.LANCZOS)
    tile = Image.new("RGB", (cell_size, cell_size), (232, 232, 232))
    x = (cell_size - glyph.width) // 2
    y = (cell_size - glyph.height) // 2
    tile.paste((45, 45, 45), (x, y), glyph)
    return tile


def render_blueprint(indices, colors, cell_size, labels=True):
    """绘制外围坐标格、内部色块、细网格及可选色号。"""
    height, width = indices.shape
    canvas_width, canvas_height = (width + 2) * cell_size, (height + 2) * cell_size
    # 灰底同时覆盖四角，四角不填写任何编号。
    image = Image.new("RGB", (canvas_width, canvas_height), (232, 232, 232))
    for x in range(1, width + 1):
        tile = coordinate_tile(x, cell_size)
        image.paste(tile, (x * cell_size, 0))
        image.paste(tile, (x * cell_size, (height + 1) * cell_size))
    for y in range(1, height + 1):
        tile = coordinate_tile(y, cell_size)
        image.paste(tile, (0, y * cell_size))
        image.paste(tile, ((width + 1) * cell_size, y * cell_size))
    draw = ImageDraw.Draw(image)
    rgbs = [tuple(bytes.fromhex(c["hex"][1:])) for c in colors]
    text_colors = ["black" if relative_luminance(rgb) >= (0.0525 ** 0.5 - 0.05) else "white" for rgb in rgbs]
    # 根据最长色号统一选择字体，保持整张图纸一致。
    font = choose_font(max(1, int(cell_size * 0.55)))
    if labels:
        for size in range(max(1, int(cell_size * 0.55)), 0, -1):
            candidate = choose_font(size)
            boxes = [draw.textbbox((0, 0), c.get("label", c["code"]), font=candidate) for c in colors]
            font = candidate
            if max(box[2] - box[0] for box in boxes) <= max(1, cell_size - 2) and max(box[3] - box[1] for box in boxes) <= max(1, cell_size - 2):
                break
    for y in range(height):
        for x in range(width):
            idx = int(indices[y, x])
            # 内部图案整体向右、向下各偏移一个坐标格。
            x0, y0 = (x + 1) * cell_size, (y + 1) * cell_size
            draw.rectangle((x0, y0, x0 + cell_size - 1, y0 + cell_size - 1), fill=rgbs[idx])
            if labels:
                label = colors[idx].get("label", colors[idx]["code"])
                box = draw.textbbox((0, 0), label, font=font)
                tx = x0 + (cell_size - (box[2] - box[0])) / 2 - box[0]
                ty = y0 + (cell_size - (box[3] - box[1])) / 2 - box[1]
                draw.text((tx, ty), label, fill=text_colors[idx], font=font)
    # 细线覆盖整个画布，包括四周坐标格及画布最外边缘。
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    grid = ImageDraw.Draw(overlay)
    for x in range(0, canvas_width, cell_size):
        grid.line((x, 0, x, canvas_height - 1), fill=(80, 80, 80, 100))
    for y in range(0, canvas_height, cell_size):
        grid.line((0, y, canvas_width - 1, y), fill=(80, 80, 80, 100))
    grid.line((canvas_width - 1, 0, canvas_width - 1, canvas_height - 1), fill=(80, 80, 80, 100))
    grid.line((0, canvas_height - 1, canvas_width - 1, canvas_height - 1), fill=(80, 80, 80, 100))
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def write_csv(path, colors, counts, total):
    """按用量降序写入 UTF-8 BOM CSV，便于常见表格软件打开。"""
    with open(path, "w", encoding="utf-8-sig", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(["色号", "HEX", "颗数", "占比"])
        for index, count in counts:
            writer.writerow([colors[index]["code"], colors[index]["hex"].upper(), count, "{:.2%}".format(count / total)])


def write_pool_csv(path, colors, counts, total):
    """写入所有池子颜色，包括没有使用的颜色。"""
    with open(path, "w", encoding="utf-8-sig", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(["序号", "色号", "HEX", "颗数", "占比"])
        for index, count in counts:
            color = colors[index]
            writer.writerow([color["code"], color["mard_code"], color["hex"], count, "{:.2%}".format(count / total)])


def positive_int(value):
    try:
        number = int(value)
        if number <= 0:
            raise ValueError
        return number
    except ValueError:
        raise argparse.ArgumentTypeError("必须是正整数")


def nonnegative_int(value):
    """解析允许零的整数。"""
    try:
        number = int(value)
        if number < 0:
            raise ValueError
        return number
    except ValueError:
        raise argparse.ArgumentTypeError("必须是非负整数")


def main(argv=None):
    parser = argparse.ArgumentParser(description="将图片转换为 MARD 色卡拼豆图纸")
    parser.add_argument("input", help="输入图片路径")
    parser.add_argument("-o", "--output", help="输出 PNG 路径，默认 output/<输入文件名>_pindou.png")
    parser.add_argument("--cell-size", type=positive_int, default=24, help="每格像素，默认 24")
    parser.add_argument("--width", type=positive_int, default=80, help="网格宽度，默认 80")
    parser.add_argument("--height", type=positive_int, default=121, help="网格高度，默认 121")
    parser.add_argument("--csv", help="用量清单路径，默认与 PNG 同名")
    parser.add_argument("--no-label", action="store_true", help="不绘制色号文字，保留坐标标尺")
    parser.add_argument("--palette", default=str(BASE_DIR / "data" / "mard221.json"), help="色卡 JSON 路径")
    parser.add_argument("--dpi", type=positive_int, default=300, help="PNG DPI 元数据，默认 300")
    parser.add_argument("--max-colors", type=nonnegative_int, default=0, help="限制最多使用多少种颜色，0 表示不限制；指定 --colors 时以颜色池为准")
    parser.add_argument("--colors", help="指定颜色池：逗号分隔的 HEX 或 MARD 色号，或颜色池文件路径")
    parser.add_argument("--resample", choices=["lanczos", "nearest", "mode", "vote"], default="lanczos",
                        help="下采样：lanczos 平滑（默认）；nearest 最近像素；mode 按面积选原始 RGB 众数；vote 先匹配色池再按面积投票")
    parser.add_argument("--pool-labels", choices=["index", "code"], default="index",
                        help="--colors 模式下格子里写什么：index 池内序号（默认）或 code 色号")
    parser.add_argument("--quantize", choices=["prune", "kmeans"], default="kmeans", help="限色算法：kmeans 聚类（默认，保形好）或 prune 按用量剪枝")
    args = parser.parse_args(argv)
    output = Path(args.output) if args.output else Path("output") / (Path(args.input).stem + "_pindou.png")
    csv_path = Path(args.csv) if args.csv else output.with_suffix(".csv")
    try:
        if output.resolve() == csv_path.resolve():
            raise ValueError("PNG 和 CSV 输出路径不能相同")
        self_check()
        if args.colors is not None:
            colors = load_color_pool(args.colors, load_palette(BASE_DIR / "data" / "mard221.json"))
            if args.pool_labels == "code":
                for color in colors:
                    color["label"] = color["mard_code"] if color["mard_code"] != "-" else color["code"]
        else:
            colors = load_palette(args.palette)
        palette_rgb = np.array([list(bytes.fromhex(c["hex"][1:])) for c in colors], dtype=np.uint8)
        image = prepare_image(args.input, args.width, args.height,
                              Image.Resampling.NEAREST if args.resample == "nearest" else Image.Resampling.LANCZOS)
        palette_lab = rgb_to_lab(palette_rgb)
        indices = nearest_color(np.asarray(image), palette_lab)
        if args.max_colors and args.colors is None:
            if args.quantize == "kmeans":
                indices = kmeans_indices(image, palette_lab, args.max_colors)
            else:
                indices = prune_colors(indices, palette_lab, args.max_colors)
        if args.resample in ("mode", "vote"):
            pool = np.unique(indices) if args.max_colors and args.colors is None else np.arange(len(colors))
            with Image.open(args.input) as source:
                source = ImageOps.exif_transpose(source).convert("RGB")
                indices = pool[area_resample(source, args.width, args.height, palette_lab[pool], args.resample)]
        used_counts = Counter(indices.flat)
        if args.colors is not None:
            counts = sorted(((idx, used_counts[idx]) for idx in range(len(colors))), key=lambda item: (-item[1], item[0]))
        else:
            counts = sorted(used_counts.items(), key=lambda item: (-item[1], item[0]))
        result = render_blueprint(indices, colors, args.cell_size, not args.no_label)
        output.parent.mkdir(parents=True, exist_ok=True)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        result.save(output, format="PNG", dpi=(args.dpi, args.dpi))
        if args.colors is not None:
            write_pool_csv(csv_path, colors, counts, indices.size)
            print("颜色池清单（序号 / 色号 / HEX / 颗数 / 占比）：")
            for idx, count in counts:
                color = colors[idx]
                print("  {} / {} / {} / {} / {:.2%}".format(color["code"], color["mard_code"], color["hex"], count, count / indices.size))
            print("总颗数：{}；实际用到的颜色数：{} 种；池子颜色数：{} 种".format(indices.size, len(used_counts), len(colors)))
        else:
            write_csv(csv_path, colors, counts, indices.size)
            print("总颗数：{}；使用颜色：{} 种".format(indices.size, len(counts)))
            print("用量前 10：")
            for idx, count in counts[:10]:
                print("  {} {}：{} 颗（{:.2%}）".format(colors[idx]["code"], colors[idx]["hex"].upper(), count, count / indices.size))
        print("图纸：{}\n清单：{}".format(output, csv_path))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print("错误：{}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
