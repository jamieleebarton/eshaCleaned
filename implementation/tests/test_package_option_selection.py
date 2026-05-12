from __future__ import annotations

import sys
import unittest
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[2]
PLANNER = ROOT / "planner"
if str(PLANNER) not in sys.path:
    sys.path.insert(0, str(PLANNER))

from hestia.sparse_cascade import SparseCascadePlanner


class PackageOptionSelectionTests(unittest.TestCase):
    def test_subgram_spice_packages_are_not_clamped_to_one_gram(self) -> None:
        num_pkg, selected_size, selected_price, purchased, cost = (
            SparseCascadePlanner._choose_package_options(
                torch.tensor([1.0]),
                torch.tensor([[0.5, 0.9]]),
                torch.tensor([[5.99, 9.99]]),
            )
        )

        self.assertAlmostEqual(float(num_pkg[0]), 2.0)
        self.assertAlmostEqual(float(selected_size[0]), 0.5)
        self.assertAlmostEqual(float(selected_price[0]), 5.99, places=5)
        self.assertAlmostEqual(float(purchased[0]), 1.0)
        self.assertAlmostEqual(float(cost[0]), 11.98, places=2)


if __name__ == "__main__":
    unittest.main()
