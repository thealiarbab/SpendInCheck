"""
How many decimal places each currency has.

ISO 4217 divides most currencies into hundredths, but not all: 33 have no
minor unit at all (the yen, the won, the rupiah -- ¥100 is not ¥100.00),
and six Gulf and North African dinars are divided into thousandths. An
amount rounded to two places is wrong for 39 of the 162 currencies in use.

This table is generated, not typed. It comes from
`Intl.supportedValuesOf("currency")` in Node, with each currency's minor
units read from `Intl.NumberFormat(...).resolvedOptions()` -- so it is the
same data the browser formats with, and the two halves cannot disagree.
Regenerate with scripts/currencies.js when a currency is added or redenominated.

The browser needs none of this: Intl already knows. Python has no
equivalent, and the server has to know the scale to round a submitted
amount correctly, which is why it is written down here.
"""

# Currencies with no minor unit. An amount in these is a whole number.
ZERO_DECIMAL = frozenset({
    "AFN", "ALL", "BIF", "CLP", "COP", "DJF", "GNF", "HUF", "IDR", "IQD",
    "IRR", "ISK", "JPY", "KMF", "KPW", "KRW", "LAK", "LBP", "MGA", "MMK",
    "PKR", "PYG", "RWF", "SLL", "SOS", "SYP", "UGX", "VND", "VUV", "XAF",
    "XOF", "XPF", "YER",
})

# Currencies divided into thousandths -- the fils. DECIMAL(10,2) could not
# hold 1.234 KWD at all, which is what migration 002 widened the columns for.
THREE_DECIMAL = frozenset({
    "BHD", "JOD", "KWD", "LYD", "OMR", "TND",
})

# Every currency Intl knows, which is every one ISO 4217 currently lists.
ALL = (
    "AED", "AFN", "ALL", "AMD", "ANG", "AOA", "ARS", "AUD", "AWG", "AZN",
    "BAM", "BBD", "BDT", "BGN", "BHD", "BIF", "BMD", "BND", "BOB", "BRL",
    "BSD", "BTN", "BWP", "BYN", "BZD", "CAD", "CDF", "CHF", "CLP", "CNY",
    "COP", "CRC", "CUC", "CUP", "CVE", "CZK", "DJF", "DKK", "DOP", "DZD",
    "EGP", "ERN", "ETB", "EUR", "FJD", "FKP", "GBP", "GEL", "GHS", "GIP",
    "GMD", "GNF", "GTQ", "GYD", "HKD", "HNL", "HRK", "HTG", "HUF", "IDR",
    "ILS", "INR", "IQD", "IRR", "ISK", "JMD", "JOD", "JPY", "KES", "KGS",
    "KHR", "KMF", "KPW", "KRW", "KWD", "KYD", "KZT", "LAK", "LBP", "LKR",
    "LRD", "LSL", "LYD", "MAD", "MDL", "MGA", "MKD", "MMK", "MNT", "MOP",
    "MRU", "MUR", "MVR", "MWK", "MXN", "MYR", "MZN", "NAD", "NGN", "NIO",
    "NOK", "NPR", "NZD", "OMR", "PAB", "PEN", "PGK", "PHP", "PKR", "PLN",
    "PYG", "QAR", "RON", "RSD", "RUB", "RWF", "SAR", "SBD", "SCR", "SDG",
    "SEK", "SGD", "SHP", "SLE", "SLL", "SOS", "SRD", "SSP", "STN", "SVC",
    "SYP", "SZL", "THB", "TJS", "TMT", "TND", "TOP", "TRY", "TTD", "TWD",
    "TZS", "UAH", "UGX", "USD", "UYU", "UZS", "VES", "VND", "VUV", "WST",
    "XAF", "XCD", "XCG", "XDR", "XOF", "XPF", "XSU", "YER", "ZAR", "ZMW",
    "ZWG", "ZWL",
)

DEFAULT = "INR"

# The widest scale any currency needs, and what the money columns are stored
# at. Amounts cross the wire at this scale so nothing is lost in transit;
# each amount is rounded to its own currency's scale on the way in.
MAX_DECIMALS = 3


def decimals(code):
    """How many decimal places this currency is divided into."""
    if code in ZERO_DECIMAL:
        return 0
    if code in THREE_DECIMAL:
        return 3
    return 2


def is_known(code):
    """True if this is a currency the app can hold money in."""
    return code in ALL
