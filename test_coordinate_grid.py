"""检查默认、10 像素和无色号样例图的坐标与用量。"""

import csv
from PIL import Image, ImageDraw, ImageChops
from pindou import choose_coordinate_font, coordinate_tile


def reference(number, cell):
    # 独立在空白小图上按给定数字重新排版，不从成品图中取得内容。
    text = str(number)
    limit = max(1, cell - 2)
    for font_size in range(max(1, cell - 2), 0, -1):
        font = choose_coordinate_font(font_size)
        bounds = font.getbbox(text)
        if bounds[2] - bounds[0] <= limit and bounds[3] - bounds[1] <= limit:
            break
    glyph = Image.new('L', (max(1, bounds[2] - bounds[0]), max(1, bounds[3] - bounds[1])))
    ImageDraw.Draw(glyph).text((-bounds[0], -bounds[1]), text, font=font, fill=255)
    glyph.thumbnail((limit, limit), Image.Resampling.LANCZOS)
    tile = Image.new('RGB', (cell, cell), (232, 232, 232))
    tile.paste((45, 45, 45), ((cell - glyph.width) // 2, (cell - glyph.height) // 2), glyph)
    return tile


for stem, cell in [('sample_pindou', 24), ('sample_cell10', 10), ('sample_no_label', 24)]:
    with Image.open('output/' + stem + '.png') as source:
        im = source.convert('RGB')
    assert im.size == (82 * cell, 123 * cell), (stem, im.size)
    positions = [(1, 0, 1), (80, 0, 80), (1, 122, 1), (80, 122, 80),
                 (0, 1, 1), (0, 121, 121), (81, 1, 1), (81, 121, 121)]
    for x, y, value in positions:
        tile = im.crop((x*cell+1, y*cell+1, (x+1)*cell-1, (y+1)*cell-1))
        expected = reference(value, cell).crop((1, 1, cell-1, cell-1))
        assert not ImageChops.difference(tile, expected).getbbox(), (stem, x, y, value)
        assert expected.getextrema() != ((232,232),)*3, (stem, value, '数字为空')
    for x, y in [(0,0),(81,0),(0,122),(81,122)]:
        corner = im.crop((x*cell+1, y*cell+1, (x+1)*cell-1, (y+1)*cell-1))
        assert corner.getextrema() == ((232,232),)*3, (stem, x, y, '角落非空')
    with open('output/' + stem + '.csv', encoding='utf-8-sig', newline='') as f:
        total = sum(int(row['颗数']) for row in csv.DictReader(f))
    assert total == 9680, (stem, total)
    print(stem, '尺寸', im.size, '四边端点 1/80/121 像素吻合；四角为空；CSV', total)

# 检查所有可能的编号：独立坐标小图边界均为背景，文字不会写进相邻格。
for cell in (10, 24):
    for value in range(1, 122):
        tile = coordinate_tile(value, cell)
        for i in range(cell):
            assert all(tile.getpixel(p) == (232,232,232) for p in [(0,i),(cell-1,i),(i,0),(i,cell-1)]), (cell, value, i)
    print('cell-size', cell, '坐标 1..121 均未触及格边')

with Image.open('output/sample_pindou.png') as a, Image.open('output/sample_no_label.png') as b:
    for box in [(0,0,a.width,24), (0,a.height-24,a.width,a.height),
                (0,0,24,a.height), (a.width-24,0,a.width,a.height)]:
        assert not ImageChops.difference(a.crop(box), b.crop(box)).getbbox()
print('--no-label：四边标尺与默认图逐像素一致')
