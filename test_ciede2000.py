#!/usr/bin/env python3
"""用 Sharma 等（2005）的 34 组数据验证 CIEDE2000。"""

import unittest

from ciede2000_reference import REFERENCE_DATA
from pindou import ciede2000


class TestCIEDE2000(unittest.TestCase):
    def test_reference_values(self):
        failures = []
        for index, (lab1, lab2, expected) in enumerate(REFERENCE_DATA, 1):
            actual = float(ciede2000(lab1, lab2))
            passed = abs(actual - expected) <= 0.00005
            print("{} 第 {:02d} 组：实际 {:.6f}，参考 {:.4f}".format("PASS" if passed else "FAIL", index, actual, expected))
            if not passed:
                failures.append(index)
        print("汇总：{} 组通过，{} 组失败".format(len(REFERENCE_DATA) - len(failures), len(failures)))
        self.assertEqual(len(REFERENCE_DATA), 34, "参考数据应为 34 组")
        self.assertEqual(failures, [], "失败组号：{}".format(failures))


if __name__ == "__main__":
    unittest.main()
