import unittest

from inventory import Inventory, OutOfStock


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.inv = Inventory()
        self.inv.add("apple", 5)
        self.inv.add("pear", 2)

    def test_add_accumulates(self):
        self.inv.add("apple", 3)
        self.assertEqual(self.inv.count("apple"), 8)

    def test_count_unknown_is_zero(self):
        self.assertEqual(self.inv.count("kiwi"), 0)

    def test_remove_too_many(self):
        with self.assertRaises(OutOfStock):
            self.inv.remove("pear", 3)

    def test_total_value_ignores_unknown_prices(self):
        self.assertEqual(self.inv.total_value({"apple": 0.5}), 2.5)

    def test_low_stock_strictly_below_sorted(self):
        self.inv.add("fig", 1)
        self.assertEqual(self.inv.low_stock(2), ["fig"])
        self.assertEqual(self.inv.low_stock(6), ["apple", "fig", "pear"])


if __name__ == "__main__":
    unittest.main()
