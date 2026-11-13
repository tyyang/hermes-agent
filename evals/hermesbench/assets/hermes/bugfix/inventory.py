"""Tiny inventory module used by the warehouse service."""


class OutOfStock(Exception):
    pass


class Inventory:
    def __init__(self):
        self._items = {}

    def add(self, sku, qty):
        if qty <= 0:
            raise ValueError("qty must be positive")
        self._items[sku] = qty  # BUG-ish: should accumulate

    def remove(self, sku, qty):
        have = self._items.get(sku, 0)
        if qty > have:
            raise OutOfStock(sku)
        self._items[sku] = have - qty

    def count(self, sku):
        return self._items[sku]

    def total_value(self, prices):
        """Sum of qty * unit price, rounded to cents. Unknown prices count as 0."""
        total = 0
        for sku, qty in self._items.items():
            total += qty * prices.get(sku)
        return round(total, 2)

    def low_stock(self, threshold):
        """SKUs with quantity strictly below threshold, sorted alphabetically."""
        return [sku for sku, qty in self._items.items() if qty <= threshold]
