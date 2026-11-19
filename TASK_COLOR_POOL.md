# 任务：支持用户自选颜色池（--colors）

## 目标

给 `pindou.py` 增加一个 `--colors` 参数：用户手动指定"我手上有的颜色"这个池子，程序先 resize（沿用现有 `prepare_image`），然后把每个格子映射到**池子里最接近的那个颜色**，并在图纸格子里填**该颜色在池子里的序号**（1、2、3…）。

关键差异：现有流程是 221 色全色卡匹配、格子里写 MARD 色号（如 `C6`）；新模式格子里写**序号数字**，因为用户的豆子不一定是 MARD 编号体系。

## 参数定义

```
--colors <spec>
```

`<spec>` 三种写法都要支持：

1. 逗号分隔的 HEX：`--colors "#50AAF0,#9D5B3E,#2F2B2F"`
2. 逗号分隔的 MARD 色号：`--colors "C6,G7,H6"`（到 `data/mard221.json` 里查 HEX，找不到就报错并指出是哪个色号）
3. 指向文件：`--colors @pool.txt` 或 `--colors pool.json`

- 文件格式：纯文本每行一个值（支持 `#` 开头的注释行与空行），或 JSON 数组 `["#50AAF0", "C6", ...]`。每项可以是 HEX 也可以是 MARD 色号，可混用。
- 允许 `#50AAF0` 和 `50AAF0` 两种 HEX 写法（自动补 `#`），大小写不敏感。
- 去重（按 HEX 归一化后比较），**保留用户给出的顺序**，序号从 1 开始。
- 池子至少 1 色、最多不超过 221；超过或为空要给出清晰错误。

## 行为

- 给了 `--colors` 时：先 `prepare_image` 得到 resize 后的网格图，再在该池子内做 CIEDE2000 最近色匹配（复用 `ciede2000`，池子只算一次 Lab，别每像素重算）。
- 图纸每格填**序号数字**（1..N），不是 HEX、不是 MARD 色号。
- 坐标标尺、细网格、行列编号、格子底色、黑白文字自动对比度这些现有行为全部保留。
- 序号是 1 位数还是 2 位数会混在一起，字号要按最长序号统一取（现有逻辑已经是"按最长色号统一选字体"，沿用即可）。
- 输出 CSV 表头改为：`序号, 色号, HEX, 颗数, 占比`
  - `色号` 列：来自 MARD 色号的池子项就写原色号；纯 HEX 的写 `-`
  - **池子里没被用到的颜色也要出现在 CSV 里，颗数写 0**，方便备料
  - 按颗数降序，0 颗的排最后
- 终端输出：先打印颜色池清单（序号 / 色号 / HEX / 颗数 / 占比），再打印总颗数、实际用到的颜色数、池子颜色数。
- 和 `--max-colors` 互斥：同时给就报错说明二选一。
- `--colors` 不参与 `--no-label`（`--no-label` 照样隐藏格子里的序号）。

## 边界

- 默认行为（不给 `--colors`）完全不变：221 色卡匹配 + 写 MARD 色号。现有测试必须继续通过。
- 保留工作区已有修改：`pindou.py` 目前有未提交改动，含 `prune_colors`、`kmeans_indices`、`--max-colors`、`--quantize`。**不要删这些**，`--colors` 是并列新增的第三条路径。
- 代码风格跟现有文件一致：中文 docstring、简洁函数、argparse 参数带中文 help。

## 验收

在 `/Users/looyifan/.openclaw/workspace-linus/pindou` 下实际跑：

```sh
# 1) HEX 池子（16 色）
python3 pindou.py samples/myhome_beads.jpg -o output/pool16_hex.png \
  --cell-size 48 --dpi 300 \
  --colors "#50AAF0,#9D5B3E,#8D614C,#644749,#EEE9EA,#2F2B2F,#48464E,#BC0028,#C1444A,#176DAF,#B7714A,#78524B,#E6C9B7,#FFFFFF,#000000,#C77362"
# 期望：使用颜色 <= 16，格子写 1..16，CSV 有 16 行 + 表头

# 2) MARD 色号池子
python3 pindou.py samples/myhome_beads.jpg -o output/pool_mard.png --cell-size 24 --colors "C6,G7,H6,H10"

# 3) 文件池子
printf '# 我的豆子\nC6\nG7\n#FFFFFF\n\n' > /tmp/pool_test.txt
python3 pindou.py samples/myhome_beads.jpg -o output/pool_file.png --cell-size 24 --colors @/tmp/pool_test.txt

# 4) 错误路径
python3 pindou.py samples/myhome_beads.jpg -o /tmp/x.png --colors "C6,ZZ9"      # 应报错指出 ZZ9 不存在
python3 pindou.py samples/myhome_beads.jpg -o /tmp/x.png --colors "C6" --max-colors 16  # 应报错互斥

# 5) 回归
python3 test_ciede2000.py
python3 pindou.py samples/myhome_beads.jpg -o output/regress_default.png --cell-size 12
```

CSV 校验：序号连续、颗数合计 = 9680（80×121）、0 颗颜色列在末尾。

## 报告

结束时说明：新增/修改的函数与参数、三种池子写法的实测结果、CSV 表头与 0 颗行处理、跑了哪些验证及输出、仍未处理的问题。
