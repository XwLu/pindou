# 任务：图片转 MARD 221 拼豆图纸生成器

## 目标

在 `/Users/looyifan/.openclaw/workspace-linus/pindou` 下开发一个 Python 工具 `pindou.py`：
输入一张原始图片，输出一张「带 MARD 221 标准色卡序号」的拼豆图纸。

## 具体行为

1. 读取输入图片（任意常见格式），转换为 RGB。
2. 先按**保持宽高比**的方式缩放到适合的尺寸，再居中裁剪/填充，最终 resize 成 **宽 80 × 高 121** 的低分辨率图片（注意：宽 80、高 121，是竖版，不是 80x80）。
   - 缩放用高质量算法（LANCZOS），避免颜色失真。
   - 注意宽高比的正确处理，不要直接把图片压扁。
3. 遍历 80×121 网格的每个像素，取其 RGB 值，在 **MARD 221 标准色卡** 中查找最接近的颜色，得到对应色号。
   - 颜色距离必须用 **CIEDE2000**（在 Lab 空间计算），不要用简单欧氏距离。
   - 色卡数据已提供：`data/mard221.json`，结构为 `{"brand": "MARD 221", "count": 221, "colors": [{"code": "A1", "name": "A1", "hex": "#FAF4C8"}, ...]}`，共 221 色。
   - 必须实现 CIEDE2000 并**用 Sharma 等人 2005 年论文中的 34 组官方参考数据自检**，自检不通过则报错退出（这是正确性保证，请认真实现）。
   - 允许缓存匹配结果（用 RGB 到色号的 dict 缓存）以加速。
4. 生成「带序号的拼豆图片」：
   - 每个格子填该色号对应的色卡颜色。
   - 每个格子上叠加该格子的色号文字（如 `A1`、`B12`、`H7`）。
   - 格子需要放大到可读尺寸（例如每格 24px 左右，含坐标格最终为 1968×2952，可用 `--cell-size` 参数调）。
   - 文字颜色按格子背景亮度自动选黑或白，保证可读（用相对亮度判断，不要拍脑袋）。
   - 画出细网格线，覆盖图案和坐标格，方便印刷后对照。
   - 图案外增加一圈一格厚的坐标格：顶边和底边标列号 1..宽度，左边和右边标行号 1..高度。图案左上角的第一颗豆子坐标为（1，1），四角留空。
   - 坐标格与色块视觉区分，数字自动适配格子且不能溢出；坐标格不计入用量。
5. 同时输出：
   - **PNG 图纸**（带色号）
   - **CSV 用量清单**：色号、HEX、颗数、占比，按用量降序
   - 终端打印用量摘要（总颗数、用到的颜色数、Top 10）
6. CLI 设计：

```
python3 pindou.py input.jpg -o output.png
```

可用参数：
- `-o / --output` 输出图片路径（默认 `output/<输入文件名>_pindou.png`）
- `--cell-size` 每格像素，默认 24
- `--width` / `--height` 目标格子数，默认 80 / 121
- `--csv` CSV 路径（默认跟随输出图片同名 `.csv`）
- `--no-label` 不叠加图案格色号文字，保留坐标数字
- `--palette` 色卡 JSON 路径，默认 `data/mard221.json`
- `--dpi` 输出 PNG 的 DPI 元数据，默认 300

## 技术要求

- 只用标准库 + Pillow + numpy（避免引入重依赖；CIEDE2000 自己实现，不要依赖 coloraide 之类的库）。
- Python 3.9 兼容。
- 代码分函数清晰组织：`load_palette()`、`ciede2000()`、`nearest_color()`、`prepare_image()`、`render_blueprint()`、`write_csv()`、`main()`。
- 中文注释和中文 CLI 输出。
- 提供 `requirements.txt`（Pillow、numpy）。
- 提供 `README.md`：安装、用法、参数说明、示例。
- 提供 `test_ciede2000.py`：用 Sharma 2005 的 34 组参考数据做单元测试，`python3 test_ciede2000.py` 直接可跑并打印 PASS/FAIL 汇总。

## 验收标准

1. `python3 test_ciede2000.py` 全部通过（34 组参考数据）。
2. 用一张生成的测试图（渐变 + 几个色块，80×121 或更大）跑通：
   `python3 pindou.py samples/sample.png -o output/sample_pindou.png`
   → 产出 PNG，尺寸为 `(80+2)*24 x (121+2)*24`（1968×2952，含坐标格）；CSV 存在且颗数合计 = 80*121 = 9680。
3. 输出的 PNG 能正常打开，格子颜色与色卡一致，序号文字清晰可读。
4. `--cell-size 10` 与 `--no-label` 也能正常工作；坐标数字不溢出格子，`--no-label` 仍保留标尺。

## 范围与约束

- 只做上述功能，不要顺手加 UI、Web 服务、AI 生成之类的额外特性。
- 保持项目目录整洁，输出文件放 `output/`，测试样本放 `samples/`。
- 不要修改 `data/mard221.json`（这是提供的权威色卡数据）。
- 如果发现色卡数据有问题（比如某色号 HEX 格式异常），报告出来，不要擅自改。

## 环境

- 项目根目录：`/Users/looyifan/.openclaw/workspace-linus/pindou`（已是 git 仓库）
- 已预置：`data/mard221.json`（221 色）、`TASK.md`（本文件）
- 请自行安装依赖后验证（可用 venv 或系统 pip，注意别污染其他项目）。
