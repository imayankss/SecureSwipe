"""Trusted synthetic catalog for the order-integrity reference.

Every SKU, price, and currency here is **synthetic**. They are placeholders
chosen to be obviously non-commercial; they are not products, not merchant data,
and not a price list.

All money is expressed in **integer minor units**. No floating-point value is
used for currency anywhere in this package.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

#: Version of the trusted catalog. A quote binds this value.
CATALOG_VERSION = "synthetic-catalog-v1"

#: Synthetic settlement currency for the reference. Not a merchant currency.
CATALOG_CURRENCY = "XTS"

#: Minor units per major unit, stated explicitly so no caller has to assume it.
MINOR_UNITS_PER_MAJOR = 100

#: Allowlisted synthetic SKUs and their unit price in integer minor units.
CATALOG: Mapping[str, int] = MappingProxyType(
    {
        "SKU_ALPHA": 129_900,
        "SKU_BETA": 4_550,
        "SKU_GAMMA": 87_325,
    }
)

#: A later catalog version, used to demonstrate stale-quote rejection.
CATALOG_VERSION_NEXT = "synthetic-catalog-v2"

CATALOG_NEXT: Mapping[str, int] = MappingProxyType(
    {
        "SKU_ALPHA": 139_900,
        "SKU_BETA": 4_550,
        "SKU_GAMMA": 87_325,
    }
)

#: Bounds. The quantity cap applies to the MERGED quantity per SKU, and the
#: reconstructed total is overflow-guarded.
MAX_QUANTITY_PER_LINE = 100
MAX_LINES_PER_CART = 20
MAX_TOTAL_MINOR = 1_000_000_000
