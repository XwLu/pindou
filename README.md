# 图片转拼豆图纸

将图片转换为 MARD 221 色卡拼豆图纸，生成带色号、细网格和四边坐标标尺的 PNG，以及用量 CSV。采用 sRGB D65 转 CIELAB 及 CIEDE2000 色差匹配；程序每次运行前都会用 Sharma 等人在 2005 年发表的 34 组参考数据自检。原始参考数据见 Sharma、Wu、Dalal 的文章《The CIEDE2000 Color-Difference Formula: Implementation Notes, Supplementary Test Data, and Mathematical Observations》及其补充材料。

典型交付是**两**张 PNG：

| 产物 | 说明 | 用途 |
| --- | --- | --- |
| 成品效果图 `*_clean.png` | 纯色块，无网格无色号 | 用户判断"拼完好不好看" |
| 施工图 `*_blueprint.png` | 每格色号 + 细网格 + 四边坐标尺 | 照着拼、照着买豆 |

CSV 是用量清单，默认不发，用户明确要时再给。

## 安装

需要 Python 3.9 或更高版本。建议在项目目录使用独立虚拟环境：

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 快速上手

```sh
# 1) 看宽高比，决定版式（0.66 竖版 / ≥1.2 横版 / 其余补白）
python3 -c "from PIL import Image; im=Image.open('samples/x.jpg'); print(im.size, round(im.width/im.height,3))"

# 2) 成品效果图（纯色块脚本，见下文「成品效果图」）

# 3) 施工图
python3 pindou.py samples/x.jpg -o output/x_blueprint.png --cell-size 48 --dpi 300
```

## 版式选择（重要）

默认网格 80×121，网格宽高比 = **0.661**。`pindou.py` 先用 `ImageOps.fit` 居中**裁剪**再缩放，所以版式选错会把主体切掉（横图硬套竖版，猫头被裁是最常见的返工原因）。

| 原图宽高比 | 版式 | 命令 |
| --- | --- | --- |
| ≈ 0.66（竖图） | 竖版 80×121，裁剪几乎无损 | 默认参数 |
| ≥ 1.2（横图） | **横版 121×80** | `--width 121 --height 80` |
| 其余偏差大 | 竖版 + 补白（见「补白版」） | 默认 + 补边脚本 |

拿到宽高比再决定版式，不要在未知比例时直接跑。

## 命令行参数

```sh
python3 pindou.py samples/sample.png -o output/sample_pindou.png
```

默认先保持原图比例并居中裁剪，再用 LANCZOS 缩放为宽 80、高 121 格。图案外侧增加一圈坐标格，每格 24 像素，输出 PNG 尺寸为 (80 + 2) × 24 = 1968 像素宽、(121 + 2) × 24 = 2952 像素高。一般情况下，输出尺寸为 `(宽度 + 2) × cell-size` 乘以 `(高度 + 2) × cell-size`。默认图纸路径为 `output/<输入文件名>_pindou.png`，CSV 与图纸同名，放在同一目录。缺少的输出目录会自动创建。标尺上下显示列号，左右显示行号，均从 1 开始；左上角的第一颗豆子坐标为（1，1），四个角留空。标尺不计入 CSV 用量。终端显示总颗数、颜色数和用量前 10 名。CSV 的占比以百分数显示并保留两位小数，因此加总可能因四舍五入略有偏差。

| 参数 | 含义 | 默认值 |
| --- | --- | --- |
| `-o`, `--output` | 输出 PNG 路径 | `output/<输入文件名>_pindou.png` |
| `--cell-size` | 每格边长（像素） | 24 |
| `--width` | 图案宽度（格，不含坐标格） | 80 |
| `--height` | 图案高度（格，不含坐标格） | 121 |
| `--csv` | 用量 CSV 路径 | 与 PNG 同名 `.csv` |
| `--no-label` | 不绘制图案格内色号，仍保留坐标标尺与网格 | 默认绘制 |
| `--palette` | 色卡 JSON 路径 | 项目中的 `data/mard221.json` |
| `--dpi` | PNG 的 DPI 元数据 | 300 |
| `--colors` | 自选颜色池，格子里填池内序号 | 不启用 |
| `--max-colors` | 限制最多用多少种色卡色 | 0（不限制） |
| `--quantize` | 限色算法：`kmeans` 聚类 / `prune` 按用量剪枝 | `kmeans` |
| `--resample` | 下采样方式：`lanczos`、`nearest`、`mode`、`vote` | `lanczos` |
| `--pool-labels` | 颜色池图纸标注池内序号 `index` 或色号 `code` | `index` |

宽、高、格子大小和 DPI 必须是正整数。自定义色卡需提供 `colors` 数组，每项包含唯一的 `code` 和 `#RRGGBB` 格式的 `hex`。输出路径可指定到其他目录。

色号文字会根据背景相对亮度选择黑色或白色，尽量提高对比度。坐标格采用浅灰底色，字号按数字宽高自动调整，文字限制在格内。格子过小时，文字可能无法清晰显示；可增大 `--cell-size`，或使用 `--no-label` 隐藏色号（坐标数字仍会保留）。

## 成品效果图

`pindou.py` 只产带网格色号的施工图。纯色块渲染用下面的脚本，它复用 `pindou.py` 的函数，保证和施工图同源同色：

```sh
cd ~/.openclaw/workspace-linus/pindou && python3 - <<'PY'
import numpy as np
from PIL import Image
import pindou as P

colors = P.load_palette('data/mard221.json')
pal_rgb = np.array([list(bytes.fromhex(c['hex'][1:])) for c in colors], dtype=np.uint8)
pal_lab = P.rgb_to_lab(pal_rgb)

im = P.prepare_image('samples/x.jpg', 80, 121)      # 横版传 121, 80
idx = P.nearest_color(np.asarray(im), pal_lab)      # 第二个参数必须是 pal_lab（Lab 版色卡）
arr = np.repeat(np.repeat(pal_rgb[idx], 48, axis=0), 48, axis=1)
Image.fromarray(arr).save('output/x_clean.png', dpi=(300, 300))
PY
```

- 成品图尺寸 = 宽 × cell × 高 × cell（默认 48 时为 3840×5808）。
- `nearest_color` 的第二个参数必须传 `rgb_to_lab(pal_rgb)` 的结果。传 PIL Image 或裸 RGB 数组会报 `IndexError: index 237 is out of bounds for axis 0 with size 221`。
- 成品图不要带网格和坐标，否则用户看不清整体效果。

### 补白版

原图比例偏离 0.661 太多（比如 1.0 的方图）又不想裁掉内容时：按宽度缩到 80，居中贴到 80×121 的底色画布上，再走上面的 `nearest_color` 流程。底色取图里出现最多的颜色，或用户指定。

## 施工图

```sh
python3 pindou.py samples/x.jpg -o output/x_blueprint.png --cell-size 48 --dpi 300
```

- `--cell-size 48` 时尺寸 = (80+2)×48 × (121+2)×48 = 3936×5904，缩到聊天尺寸后色号仍能看清。
- 格子 24（默认）在小图或缩略图里色号会糊，交付一律用 48。
- 同名 CSV 会一起生成，按需提供。

## 自选颜色池（`--colors`）

用 `--colors` 指定用户手上真正有的颜色，程序只在池子里挑最接近的颜色，格子里写**池内序号**（1、2、3…）而不是 MARD 色号。三种写法：

```sh
# 逗号分隔 HEX
python3 pindou.py samples/a.jpg --colors "#50AAF0,#9D5B3E,#2F2B2F"
# 逗号分隔 MARD 色号
python3 pindou.py samples/a.jpg --colors "C6,G7,H6"
# 颜色池文件（txt 每行一个，支持 # 注释与空行；或 JSON 数组）
python3 pindou.py samples/a.jpg --colors @pool.txt
```

- HEX 可写 `#50AAF0` 或 `50AAF0`，大小写不敏感；按 HEX 去重，保留用户给的顺序，序号从 1 开始。
- 文件里 HEX 与 MARD 色号可以混用。
- 色号带前导零无需手工改写：`normalize_code` 会把 `A06`/`F09` 归一到色卡里的 `A6`/`F9`。色号不存在会直接报错，不会静默替换。
- 池子去重后不能超过 221 色。
- CSV 表头为 `序号, 色号, HEX, 颗数, 占比`，**池子里没用到的颜色也会输出（颗数 0）**，方便备料；按颗数降序排列。纯 HEX 项的「色号」列写 `-`。
- 同时指定 `--colors` 和 `--max-colors` 时，以颜色池为准，忽略限色数量（`--max-colors` 只在没有池子时生效）。
- 用户给的如果是**色号**而不是序号，加 `--pool-labels code`，格子里写 `G14` 这样的色号；默认 `index` 写 1..N。判断依据：用户按色号买豆就写色号，只关心颗数就写序号。
- 常用池子存成 `pool<N>.txt`（如 `pool16.txt`、`pool_user16.txt`），用户说"还用上次的颜色"直接复用。

**先压色再用池子的正确顺序**：先 `--max-colors N --quantize kmeans` 跑一次，从生成的 CSV 取那 N 个色号写成池子文件，再用 `--colors` 出图。不要凭感觉手写近似色号。

## 限制用色数量

`--max-colors` 把输出压到 N 色以内，适合不指定池子、只想减少杂色的场景：

```sh
python3 pindou.py samples/a.jpg --max-colors 16                    # 默认 kmeans 聚类，保形最好
python3 pindou.py samples/a.jpg --max-colors 16 --quantize prune   # 按用量剪枝，更快但边界更糊
```

- `kmeans`：Lab 空间按像素频次加权聚类，取聚类成员的真实 RGB 加权均值再映射色卡。**保形好，优先用**。
- `prune`：保留用量最多的 N 色、其余就近并入。色数少时会把细节糊进背景（沙发上的猫被并成天蓝），只在 N ≥ 40 时可用。

实测参考（多色插画 MyHome 原生 85 色）：→ 40 色肉眼几乎无差；→ 16 色是临界点，再压图形明显变形。用户报价前先把这条下限告诉他，不要无脑按数字压。

## 下采样方式

使用 `--resample` 选择居中裁剪后的缩放方式：

| 模式 | 行为 | 用于 |
| --- | --- | --- |
| `lanczos` | 默认平滑插值 | 照片、渐变 |
| `nearest` | 取最近源像素 | 快速检查细线是否丢失 |
| `mode` | 格内原始 RGB 众数（按覆盖面积） | 源图本身色就少 |
| `vote` | **先量化到色池，再按亚像素覆盖面积投票** | 硬边插画、已定色池 —— 首选 |

`mode` 和 `vote` 使用指定的 `--colors` 色池；未指定色池时，若启用 `--max-colors`，先用 `--quantize` 从 LANCZOS 结果选择色号，再回到原图采样；否则使用完整色卡。

```sh
python3 pindou.py samples/a.jpg --colors @pool.txt --resample vote
```

`LANCZOS` 下采样会把相邻两色平均成第三色，再映射到有限色池就产生脏边（`Q(Σwᵢxᵢ) ≠ ΣQ(xᵢ)`）。用户抱怨"纹理边缘混出新颜色"时，不要改算法思路，直接换 `vote`。`vote` 全程不产生新颜色，黑白描边不再糊；代价是中间调层次略少（渐变会分层）。识别像素画可看边界位置是否有稳定周期（MyHome 源图 832×1256，原生网格约 10px）。默认仍是 `lanczos`。

## 验收

跑完按这几条核对，任一条不符就是没出对：

1. **CSV 颗数合计 = 宽 × 高**（默认 80×121 = 9680）。
2. **施工图尺寸 = (宽+2) × cell × (高+2) × cell**（默认 82×123 × 48 = 3936×5904）。
3. **成品图尺寸 = 宽 × cell × 高 × cell**。
4. **限色后色数 = `--max-colors`**（数 CSV 行数）。
5. **池子模式**：实际用色数 ≤ 池子色数，CSV 行数 = 池子去重后色数（含颗数 0 的行）。
6. 施工图有坐标尺、格内有色号；成品图是纯色块、无网格。
7. 主体没被裁掉（对照原图）。

## 其他示例

```sh
python3 pindou.py samples/sample.png -o output/small.png --cell-size 10
python3 pindou.py samples/sample.png -o output/no_label.png --no-label
python3 pindou.py samples/sample.png --width 40 --height 60 --dpi 150 --csv output/counts.csv
python3 test_ciede2000.py
```

`python3 test_coordinate_grid.py` 用 `tests/fixtures/` 里固化的 `sample_pindou`、`sample_cell10`、`sample_no_label` 三组 PNG+CSV 检查坐标端点、边界和 CSV 颗数，无需先生成产物。要更新夹具时，按需重跑对应命令后把产物拷进 `tests/fixtures/`。

## 目录

```
pindou/
├── pindou.py              主程序
├── data/mard221.json      MARD 221 色卡
├── samples/               测试与历史素材
├── output/                产出（PNG + CSV）
├── test_*.py              自检与单测
├── pool*.txt              常用颜色池
└── TASK*.md               历史任务说明
```
