# 图片转拼豆图纸

将图片转换为 MARD 221 色卡拼豆图纸，生成带色号、细网格的 PNG 和用量 CSV。采用 sRGB D65 转 CIELAB 及 CIEDE2000 色差匹配；程序每次运行前都会用 Sharma 等人在 2005 年发表的 34 组参考数据自检。原始参考数据见 Sharma、Wu、Dalal 的文章《The CIEDE2000 Color-Difference Formula: Implementation Notes, Supplementary Test Data, and Mathematical Observations》及其补充材料。

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

默认先保持原图比例并居中裁剪，再用 LANCZOS 缩放为宽 80、高 121 格；每格 24 像素，输出 1920 × 2904 PNG。默认图纸路径为 `output/<输入文件名>_pindou.png`，CSV 与图纸同名，放在同一目录。缺少的输出目录会自动创建。终端显示总颗数、颜色数和用量前 10 名。CSV 的占比以百分数显示并保留两位小数，因此加总可能因四舍五入略有偏差。

| 参数 | 含义 | 默认值 |
| --- | --- | --- |
| `-o`, `--output` | 输出 PNG 路径 | `output/<输入文件名>_pindou.png` |
| `--cell-size` | 每格边长（像素） | 24 |
| `--width` | 网格宽度（格） | 80 |
| `--height` | 网格高度（格） | 121 |
| `--csv` | 用量 CSV 路径 | 与 PNG 同名 `.csv` |
| `--no-label` | 不绘制色号文字，仍保留网格 | 默认绘制 |
| `--palette` | 色卡 JSON 路径 | 项目中的 `data/mard221.json` |
| `--dpi` | PNG 的 DPI 元数据 | 300 |

宽、高、格子大小和 DPI 必须是正整数。自定义色卡需提供 `colors` 数组，每项包含唯一的 `code` 和 `#RRGGBB` 格式的 `hex`。输出路径可指定到其他目录。

```sh
python3 pindou.py samples/sample.png -o output/small.png --cell-size 10
python3 pindou.py samples/sample.png -o output/no_label.png --no-label
python3 pindou.py samples/sample.png --width 40 --height 60 --dpi 150 --csv output/counts.csv
python3 test_ciede2000.py
```

色号文字会根据背景相对亮度选择黑色或白色，尽量提高对比度。格子过小时，文字可能无法清晰显示，可增大 `--cell-size` 或使用 `--no-label`。
