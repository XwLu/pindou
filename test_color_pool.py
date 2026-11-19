#!/usr/bin/env python3
"""颜色池解析和用量清单的回归测试。"""
import csv
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from pindou import BASE_DIR, load_color_pool, load_palette, nearest_color, rgb_to_lab, write_pool_csv


class ColorPoolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.palette = load_palette(BASE_DIR / "data" / "mard221.json")

    def test_mixed_dedup_keeps_first_entry(self):
        hex_value = self.palette[0]["hex"]
        colors = load_color_pool("{},a1,{},C6".format(hex_value.lower(), hex_value[1:]), self.palette)
        self.assertEqual([c["code"] for c in colors], ["1", "2"])
        self.assertEqual([c["mard_code"] for c in colors], ["-", "C6"])
        self.assertEqual(colors[0]["hex"], hex_value.upper())

    def test_text_and_json_files(self):
        with tempfile.TemporaryDirectory() as directory:
            text_path = Path(directory) / "pool.txt"
            text_path.write_text("# 注释\nC6\n#ffffff\n\n", encoding="utf-8")
            json_path = Path(directory) / "pool.json"
            json_path.write_text(json.dumps(["C6", "#ffffff"]), encoding="utf-8")
            self.assertEqual(load_color_pool("@" + str(text_path), self.palette), load_color_pool(str(json_path), self.palette))

    def test_invalid_and_limits(self):
        for spec in ("", "C6,", "C6,ZZ9", ","):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                load_color_pool(spec, self.palette)
        valid = ",".join("{:06X}".format(i) for i in range(221))
        self.assertEqual(len(load_color_pool(valid + ",#000000", self.palette)), 221)
        too_many = valid + ",0000DD"
        with self.assertRaisesRegex(ValueError, "221"):
            load_color_pool(too_many, self.palette)

    def test_matching_and_csv_zero_count(self):
        colors = load_color_pool("#000000,#FFFFFF,#FF0000", self.palette)
        rgb = np.array([[0, 0, 0], [250, 250, 250]], dtype=np.uint8)
        palette_rgb = np.array([list(bytes.fromhex(c["hex"][1:])) for c in colors], dtype=np.uint8)
        np.testing.assert_array_equal(nearest_color(rgb, rgb_to_lab(palette_rgb)), [0, 1])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pool.csv"
            write_pool_csv(path, colors, [(0, 1), (1, 1), (2, 0)], 2)
            with path.open(encoding="utf-8-sig", newline="") as source:
                reader = csv.DictReader(source)
                self.assertEqual(reader.fieldnames, ["序号", "色号", "HEX", "颗数", "占比"])
                rows = list(reader)
            self.assertEqual(rows[-1], {"序号": "3", "色号": "-", "HEX": "#FF0000", "颗数": "0", "占比": "0.00%"})


if __name__ == "__main__":
    unittest.main()
