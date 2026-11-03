# 图片转拼豆图纸

将图片转换为 MARD 221 色卡拼豆图纸，生成带色号、细网格和四边坐标标尺的 PNG，以及用量 CSV。采用 sRGB D65 转 CIELAB 及 CIEDE2000 色差匹配；程序每次运行前都会用 Sharma 等人在 2005 年发表的 34 组参考数据自检。原始参考数据见 Sharma、Wu、Dalal 的文章《The CIEDE2000 Color-Difference Formula: Implementation Notes, Supplementary Test Data, and Mathematical Observations》及其补充材料。

## 安装

需要 Python 3.9 或更高版本。建议在项目目录使用独立虚拟环境：

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 使用

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

宽、高、格子大小和 DPI 必须是正整数。自定义色卡需提供 `colors` 数组，每项包含唯一的 `code` 和 `#RRGGBB` 格式的 `hex`。输出路径可指定到其他目录。

```sh
python3 pindou.py samples/sample.png -o output/small.png --cell-size 10
python3 pindou.py samples/sample.png -o output/no_label.png --no-label
python3 pindou.py samples/sample.png --width 40 --height 60 --dpi 150 --csv output/counts.csv
python3 test_ciede2000.py
```

生成 `output/sample_pindou.png`、`output/sample_cell10.png` 和 `output/sample_no_label.png` 后，可运行 `python3 test_coordinate_grid.py` 检查坐标端点、边界和 CSV 颗数。

色号文字会根据背景相对亮度选择黑色或白色，尽量提高对比度。坐标格采用浅灰底色，字号按数字宽高自动调整，文字限制在格内。格子过小时，文字可能无法清晰显示；可增大 `--cell-size`，或使用 `--no-label` 隐藏色号（坐标数字仍会保留）。
