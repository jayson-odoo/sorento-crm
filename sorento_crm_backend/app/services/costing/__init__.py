"""Product costing (lane PRODUCT-COSTING): the Costing page's rates, cost basis and party data.

`formula` is pure Decimal math, `rates` the dated exchange rates, `basis` the cost behind a
product on a date, `page` everything the Costing routes serve. Nothing in this package writes
`products.list_price` or talks to AutoCount.
"""
