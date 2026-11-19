# 任务：增加下采样模式 `--resample`，解决硬边处混出"第三种颜色"

## 背景 / 问题

现在 `prepare_image` 用 `ImageOps.fit(..., LANCZOS)` 把原图缩到网格尺寸，然后每格在色池里找最近色。

重采样是 `y = Σ wᵢxᵢ`，量化是 `Q(y)`。问题在于 `Q(Σ wᵢxᵢ) ≠ Σ Q(xᵢ)`：黑白边界各占一半时得到中灰，落到 16 色池里被迫挑一个既不是黑也不是白的色，于是描边糊、像素画出现脏边/毛刺。LANCZOS 的负权重还会在硬边两侧产生振铃。

## 目标

新增 `--resample {lanczos,nearest,mode,vote}`，**默认 `lanczos`，默认行为一个字节都不能变**。

- `lanczos`：现有行为（`ImageOps.fit` + LANCZOS）。保持为默认值。
- `nearest`：`ImageOps.fit` + `Image.Resampling.NEAREST`。快、绝不混色，但会漏细线。
- `mode`：面积加权**众数**下采样——每个目标格统计其覆盖范围内的源像素 RGB 众数（票数最高者；平票取格中心最近的那个候选），再用该 RGB 去色池找最近色。不经过任何 RGB 平均。
- `vote`：**先量化再投票**（推荐）——先把源图每个像素映射到色池索引（CIEDE2000），再对每个目标格按**实际覆盖面积**对色号投票，取票数最高的索引。全程不产生新颜色。

## 详细的裁剪与覆盖计算

三种新模式都必须先做和 `ImageOps.fit` 完全一致的居中裁剪（保持现有构图，不要改变裁切结果），得到 `(W0, H0)` 的裁剪图，再做重采样。

覆盖面积计算要求**精确到亚像素**，不能近似成整数边界：

- 目标格 `x` 覆盖源图横向区间 `[x * W0 / W, (x+1) * W0 / W)`
- 一个源像素 `i` 可能与 1~2 个目标格相交，权重 = 重叠宽度 / 格宽（纵向同理）
- 二维权重 = 横权重 × 纵权重，同一格内所有权重之和为 1（允许浮点误差）

实现建议：对横向预计算每个源列的 `(cell_x, weight)`（可能两段），纵向同理，然后对 2D 用广播或按行累加，避免 Python 双层循环遍历百万像素。**要求 832×1256 → 80×121 在 10 秒内跑完。**

`vote` 阶段的累加用 `np.add.at` 到一个 `(H, W, K)` 的 float32 票数表（K=色池大小），最后 `argmax`。

## 与现有参数的关系

`--resample vote` 需要一个"投票用的色池"。判定顺序：

1. 给了 `--colors` → 用该颜色池
2. 给了 `--max-colors` → 先用**现有** `--quantize` 逻辑在 LANCZOS 结果上算出受限色号集合（复用 `kmeans_indices` / `prune_colors`，不要改它们），把这个集合当作投票色池，再回到**原始分辨率**重新投票
3. 都没有 → 用 221 色全色卡

`--resample mode` 同理：众数选出的 RGB 再映射到上述色池。

`--resample lanczos` 与 `nearest` 保持现有流程原样（`nearest` 只是把 method 换掉，后面的匹配/限色流程完全不动）。

## 边界

- 默认（不传 `--resample`）**必须与改动前逐像素完全一致**。改完请自己验证：用 `samples/myhome_pixel.jpg` 默认参数生成 PNG，与 `/tmp/baseline_default.png` 对比，要求 0 像素差异。
- 保留所有现有功能：`--colors` / `--pool-labels` / `--max-colors` / `--quantize` / `--no-label` / `--palette` / `--dpi` / `--cell-size`。
- 代码风格跟现有文件一致：中文 docstring、简洁函数、argparse 参数带中文 help。
- 新增 `--resample` 的 help 文本要写清楚各模式区别。
- 不要改 `render_blueprint`、`write_pool_csv`、`ciede2000`、`rgb_to_lab`。

## 新增测试

新建 `test_resample.py`（用 unittest，跟现有测试风格一致），至少覆盖：

1. **`vote` 不造新色**：4×4 硬边棋盘（纯黑 0,0,0 / 纯白 255,255,255，源图 320×320，目标 80×80，色池 = 黑+白），断言输出索引只含黑、白两种，且黑白数量完全相等（各 3200）。
2. **`lanczos` 同图会造脏色**：同一张棋盘用 `lanczos` 跑，断言出现了既非黑也非白的中间色（≥1 格），这就是问题的最小复现。
3. **`mode` 不造新色**：同棋盘 + 色池含黑色和白色，断言输出只有这两色。
4. **`nearest` 不造新色**：同棋盘，断言输出只有这两色。
5. **面积权重和 = 1**：直接单元测试权重计算函数——对随机 `W0, H0, W, H`，每一格内所有权重之和 ≈ 1.0（`atol=1e-6`），且每个源像素贡献给各格的总权重 ≈ 1.0。
6. **整数倍缩放 `vote` 无损**：源图 320×320 纯色块（每块 40×40 纯色，4 色），目标 8×8，`vote` 结果每个格子都等于对应块的颜色索引。

测试要能秒级跑完，不要用真实照片。

## 验收

在 `/Users/looyifan/.openclaw/workspace-linus/pindou` 下实际执行并把输出贴回来：

```sh
# 1) 现有测试全过
python3 test_ciede2000.py
python3 test_color_pool.py
python3 test_coordinate_grid.py
# 2) 新增测试
python3 test_resample.py
# 3) 默认行为零差异（关键！）
python3 pindou.py samples/myhome_pixel.jpg -o /tmp/after_default.png --cell-size 48 --dpi 300
python3 -c "
from PIL import Image, ImageChops
a=Image.open('/tmp/baseline_default.png').convert('RGB'); b=Image.open('/tmp/after_default.png').convert('RGB')
print('size', a.size, b.size); print('diff bbox', ImageChops.difference(a,b).getbbox())
"
# 期望 diff bbox 为 None
# 4) 四种模式都要能跑通（用用户 16 色池）
python3 pindou.py samples/myhome_pixel.jpg -o output/px16_lanczos.png --cell-size 48 --dpi 300 --colors @pool_user16.txt --pool-labels code --resample lanczos
python3 pindou.py samples/myhome_pixel.jpg -o output/px16_nearest.png --cell-size 48 --dpi 300 --colors @pool_user16.txt --pool-labels code --resample nearest
python3 pindou.py samples/myhome_pixel.jpg -o output/px16_mode.png    --cell-size 48 --dpi 300 --colors @pool_user16.txt --pool-labels code --resample mode
python3 pindou.py samples/myhome_pixel.jpg -o output/px16_vote.png    --cell-size 48 --dpi 300 --colors @pool_user16.txt --pool-labels code --resample vote
# 期望：四张都生成成功，各带 CSV，16 色全部列出
# 5) vote 与 --max-colors 组合可用
python3 pindou.py samples/myhome_pixel.jpg -o /tmp/px_vote_k16.png --colors @pool_user16.txt --resample vote --max-colors 0
# 6) 非法值报错清晰
python3 pindou.py samples/myhome_pixel.jpg -o /tmp/x.png --resample foo
# 期望：argparse 报错并列出可选值
```

## 报告

完成后在最后一条消息里说明：

- 四种模式的实际耗时（832×1256 → 80×121）
- 默认零差异验证的 diff bbox 实际结果
- `vote` 相比 `lanczos` 在 `samples/myhome_pixel.jpg` 上的用量差异（哪些色变多/变少）
- 你对哪种输入该用哪种模式的判断
