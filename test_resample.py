#!/usr/bin/env python3
"""面积重采样、裁剪和颜色投票的回归测试。"""
import contextlib
import csv
import io
import tempfile
from pathlib import Path
import unittest

import numpy as np
from PIL import Image, ImageOps

from pindou import (BASE_DIR, area_resample, axis_weights, fit_box, kmeans_indices,
                    load_palette, main, nearest_color, prepare_image, prune_colors, rgb_to_lab)


class ResampleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        y, x = np.indices((320, 320))
        cls.checker = Image.fromarray(np.repeat((((x // 80 + y // 80) % 2) * 255).astype(np.uint8)[..., None], 3, axis=2))
        cls.bw = rgb_to_lab(np.array([[0, 0, 0], [255, 255, 255]], dtype=np.uint8))

    def test_vote_no_new_color(self):
        result = area_resample(self.checker, 80, 80, self.bw, "vote")
        np.testing.assert_array_equal(np.bincount(result.ravel(), minlength=2), [3200, 3200])

    def test_lanczos_creates_intermediate_color(self):
        labs = rgb_to_lab(np.array([[0, 0, 0], [255, 255, 255], [32, 32, 32], [223, 223, 223]], dtype=np.uint8))
        resized = ImageOps.fit(self.checker, (80, 80), method=Image.Resampling.LANCZOS)
        self.assertTrue(np.any(nearest_color(resized, labs) >= 2))

    def test_mode_no_new_color(self):
        result = area_resample(self.checker, 80, 80, self.bw, "mode")
        np.testing.assert_array_equal(np.bincount(result.ravel(), minlength=2), [3200, 3200])

    def test_nearest_no_new_color(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checker.png"
            self.checker.save(path)
            image = prepare_image(path, 80, 80, Image.Resampling.NEAREST)
            np.testing.assert_array_equal(np.bincount(nearest_color(image, self.bw).ravel(), minlength=2), [3200, 3200])

    def test_area_weights(self):
        rng = np.random.default_rng(7)
        for _ in range(30):
            source_w, source_h, width, height = rng.integers(1, 51, size=4)
            xp, xc, xw = axis_weights(0, source_w, width)
            yp, yc, yw = axis_weights(0, source_h, height)
            cell_weights = np.zeros((height, width))
            source_weights = np.zeros((source_h, source_w))
            area = yw[:, None] * xw[None, :]
            np.add.at(cell_weights, (yc[:, None], xc[None, :]), area / (source_w / width * source_h / height))
            np.add.at(source_weights, (yp[:, None], xp[None, :]), area)
            np.testing.assert_allclose(cell_weights, 1, atol=1e-6, rtol=0)
            np.testing.assert_allclose(source_weights, 1, atol=1e-6, rtol=0)

    def test_vote_integer_scaling(self):
        colors = np.array([[0, 0, 0], [255, 255, 255], [255, 0, 0], [0, 0, 255]], dtype=np.uint8)
        y, x = np.indices((320, 320))
        expected = (x // 40 + y // 40) % 4
        image = Image.fromarray(colors[expected])
        np.testing.assert_array_equal(area_resample(image, 8, 8, rgb_to_lab(colors), "vote"), expected[::40, ::40])

    def test_fractional_cell_overlap(self):
        colors = np.array([[0, 0, 0], [255, 255, 255]], dtype=np.uint8)
        image = Image.fromarray(colors[np.tile([1, 0, 1, 0, 0], (5, 1))])
        expected = [[1, 0], [1, 0]]
        for method in ("mode", "vote"):
            with self.subTest(method=method):
                np.testing.assert_array_equal(area_resample(image, 2, 2, rgb_to_lab(colors), method), expected)

    def test_mode_tie_center(self):
        colors = np.array([[0, 0, 0], [255, 255, 255]], dtype=np.uint8)
        image = Image.fromarray(colors[np.array([[0, 1, 1, 0]])])
        self.assertEqual(area_resample(image, 1, 1, rgb_to_lab(colors), "mode")[0, 0], 1)

    def test_fractional_crop_matches_fit_box(self):
        # 在非整数裁剪边界上，最边缘的源像素只贡献其重叠部分。
        self.assertEqual(fit_box(5, 4, 1, 1), (0.5, 0.0, 4.5, 4.0))
        colors = np.array([[0, 0, 0], [255, 255, 255]], dtype=np.uint8)
        image = Image.fromarray(colors[np.tile([0, 1, 0, 1, 0], (4, 1))])
        xp, _, weights = axis_weights(0.5, 4.5, 1)
        np.testing.assert_array_equal(xp, [0, 1, 2, 3, 4])
        np.testing.assert_allclose(weights, [0.5, 1, 1, 1, 0.5])
        self.assertEqual(area_resample(image, 1, 1, rgb_to_lab(colors), "vote")[0, 0], 0)


    def test_restricted_palette_and_pool_priority(self):
        colors = load_palette(BASE_DIR / "data" / "mard221.json")
        palette = rgb_to_lab(np.array([list(bytes.fromhex(c["hex"][1:])) for c in colors], dtype=np.uint8))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.png"
            self.checker.resize((8, 8), Image.Resampling.NEAREST).save(path)
            preview = prepare_image(path, 4, 4)
            for method in ("mode", "vote"):
                for quantize in ("kmeans", "prune"):
                    with self.subTest(method=method, quantize=quantize):
                        if quantize == "kmeans":
                            selected = kmeans_indices(preview, palette, 2)
                        else:
                            selected = prune_colors(nearest_color(preview, palette), palette, 2)
                        allowed = {colors[index]["code"] for index in np.unique(selected)}
                        output = Path(directory) / (method + quantize + ".png")
                        with contextlib.redirect_stdout(io.StringIO()):
                            result = main([str(path), "-o", str(output), "--width", "4", "--height", "4",
                                           "--cell-size", "4", "--resample", method,
                                           "--max-colors", "2", "--quantize", quantize])
                        self.assertEqual(result, 0)
                        with output.with_suffix(".csv").open(encoding="utf-8-sig", newline="") as source:
                            used = {row["色号"] for row in csv.DictReader(source)}
                        self.assertTrue(used <= allowed)
            output = Path(directory) / "priority.png"
            with contextlib.redirect_stdout(io.StringIO()):
                result = main([str(path), "-o", str(output), "--width", "4", "--height", "4",
                               "--cell-size", "4", "--resample", "vote", "--max-colors", "1",
                               "--colors", "#000000,#FFFFFF"])
            self.assertEqual(result, 0)
            with output.with_suffix(".csv").open(encoding="utf-8-sig", newline="") as source:
                counts = [int(row["颗数"]) for row in csv.DictReader(source)]
            self.assertEqual(counts, [8, 8])


if __name__ == "__main__":
    unittest.main()
