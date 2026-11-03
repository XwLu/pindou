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


def prepare_image(path, width, height):
    """按目标比例居中裁剪，以 LANCZOS 缩放到网格尺寸。"""
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        return ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


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


def render_blueprint(indices, colors, cell_size, labels=True):
    """绘制色块、细网格以及居中的色号。"""
    height, width = indices.shape
    image = Image.new("RGB", (width * cell_size, height * cell_size), "white")
    draw = ImageDraw.Draw(image)
    rgbs = [tuple(bytes.fromhex(c["hex"][1:])) for c in colors]
    text_colors = ["black" if relative_luminance(rgb) >= (0.0525 ** 0.5 - 0.05) else "white" for rgb in rgbs]
    # 根据最长色号统一选择字体，保持整张图纸一致。
    font = choose_font(max(1, int(cell_size * 0.55)))
    if labels:
        for size in range(max(1, int(cell_size * 0.55)), 0, -1):
            candidate = choose_font(size)
            boxes = [draw.textbbox((0, 0), c["code"], font=candidate) for c in colors]
            font = candidate
            if max(box[2] - box[0] for box in boxes) <= max(1, cell_size - 2) and max(box[3] - box[1] for box in boxes) <= max(1, cell_size - 2):
                break
    for y in range(height):
        for x in range(width):
            idx = int(indices[y, x])
            x0, y0 = x * cell_size, y * cell_size
            draw.rectangle((x0, y0, x0 + cell_size - 1, y0 + cell_size - 1), fill=rgbs[idx])
            if labels:
                label = colors[idx]["code"]
                box = draw.textbbox((0, 0), label, font=font)
                tx = x0 + (cell_size - (box[2] - box[0])) / 2 - box[0]
                ty = y0 + (cell_size - (box[3] - box[1])) / 2 - box[1]
                draw.text((tx, ty), label, fill=text_colors[idx], font=font)
    # 半透明灰色细线兼顾深色与浅色背景。
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    grid = ImageDraw.Draw(overlay)
    for x in range(0, width * cell_size, cell_size):
        grid.line((x, 0, x, height * cell_size - 1), fill=(80, 80, 80, 100))
    for y in range(0, height * cell_size, cell_size):
        grid.line((0, y, width * cell_size - 1, y), fill=(80, 80, 80, 100))
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def write_csv(path, colors, counts, total):
    """按用量降序写入 UTF-8 BOM CSV，便于常见表格软件打开。"""
    with open(path, "w", encoding="utf-8-sig", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(["色号", "HEX", "颗数", "占比"])
        for index, count in counts:
            writer.writerow([colors[index]["code"], colors[index]["hex"].upper(), count, "{:.2%}".format(count / total)])


def positive_int(value):
    try:
        number = int(value)
        if number <= 0:
            raise ValueError
        return number
    except ValueError:
        raise argparse.ArgumentTypeError("必须是正整数")


def main(argv=None):
    parser = argparse.ArgumentParser(description="将图片转换为 MARD 色卡拼豆图纸")
    parser.add_argument("input", help="输入图片路径")
    parser.add_argument("-o", "--output", help="输出 PNG 路径，默认 output/<输入文件名>_pindou.png")
    parser.add_argument("--cell-size", type=positive_int, default=24, help="每格像素，默认 24")
    parser.add_argument("--width", type=positive_int, default=80, help="网格宽度，默认 80")
    parser.add_argument("--height", type=positive_int, default=121, help="网格高度，默认 121")
    parser.add_argument("--csv", help="用量清单路径，默认与 PNG 同名")
    parser.add_argument("--no-label", action="store_true", help="不绘制色号文字")
    parser.add_argument("--palette", default=str(BASE_DIR / "data" / "mard221.json"), help="色卡 JSON 路径")
    parser.add_argument("--dpi", type=positive_int, default=300, help="PNG DPI 元数据，默认 300")
    args = parser.parse_args(argv)
    output = Path(args.output) if args.output else Path("output") / (Path(args.input).stem + "_pindou.png")
    csv_path = Path(args.csv) if args.csv else output.with_suffix(".csv")
    try:
        if output.resolve() == csv_path.resolve():
            raise ValueError("PNG 和 CSV 输出路径不能相同")
        self_check()
        colors = load_palette(args.palette)
        palette_rgb = np.array([list(bytes.fromhex(c["hex"][1:])) for c in colors], dtype=np.uint8)
        image = prepare_image(args.input, args.width, args.height)
        indices = nearest_color(np.asarray(image), rgb_to_lab(palette_rgb))
        counts = sorted(Counter(indices.flat).items(), key=lambda item: (-item[1], item[0]))
        result = render_blueprint(indices, colors, args.cell_size, not args.no_label)
        output.parent.mkdir(parents=True, exist_ok=True)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        result.save(output, format="PNG", dpi=(args.dpi, args.dpi))
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
