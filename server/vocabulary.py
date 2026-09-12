"""What people call funds, against what funds are called.

A search can only match the words that are in the data, and the words
people use are frequently not. This is the small dictionary that closes the
gap, and it exists because of one specific event.

**SEBI's 2018 recategorisation renamed most of the industry.** Fund houses
were made to sort every scheme into a standard category and name it
accordingly, so "SBI Blue Chip Fund" became "SBI Large Cap Fund", "HDFC
Prudence" became "HDFC Balanced Advantage", and so on across every AMC.
The old names did not stop being used -- people who bought in 2015 still
say Blue Chip -- but they did stop being in the data. Typing the name of
your own fund and getting nothing is a poor answer.

Nothing here guesses. Each entry is a rename that actually happened or a
compound somebody types as one word, and an unknown word is left exactly
as typed.

**Why this rather than asking a model.** StockSaathi's AI reads the phrase
well, but it can only choose among candidates this database proposes -- and
that is deliberate, since a model naming tickers unaided invents plausible
wrong ones. So the expansion has to happen *before* the search, or the
right fund is never in the shortlist for anything to choose it. The
dictionary widens the net; the model still picks.
"""

# Words people type as one that the data writes as two. Splitting is safe
# in a way that joining is not: "bluechip" is unambiguous, where gluing
# every adjacent pair of words would match far more than was meant.
COMPOUNDS = {
    "bluechip": "blue chip",
    "largecap": "large cap",
    "midcap": "mid cap",
    "smallcap": "small cap",
    "flexicap": "flexi cap",
    "multicap": "multi cap",
    "largemidcap": "large mid cap",
    "taxsaver": "tax saver",
    "moneymarket": "money market",
    "ultrashort": "ultra short",
    "shortterm": "short term",
    "longterm": "long term",
    "govtsec": "gilt",
    "niftybees": "nifty bees",
}

# The renames themselves, as {what people say: what the data says}. Both
# sides are searched, never one replaced by the other -- "SBI Blue Chip"
# has to find the Large Cap fund, and a fund that genuinely still has "Blue
# Chip" in its name (Sundaram and Groww both kept it in parentheses) has to
# keep being findable by it.
ALIASES = {
    # The 2018 categories. "Blue chip" is the one people still say most.
    "blue chip": ["large cap"],
    "bluechip": ["large cap"],
    "top 100": ["large cap"],
    "top 200": ["large cap"],
    "prudence": ["balanced advantage"],
    "balanced": ["balanced advantage", "hybrid"],
    "opportunities": ["flexi cap", "value"],
    "equity fund": ["flexi cap"],

    # Names for the same legal thing.
    "elss": ["tax saver", "elss"],
    "tax saver": ["elss", "tax saver"],
    "tax saving": ["elss", "tax saver"],
    "80c": ["elss", "tax saver"],

    # What people call an index fund.
    "index": ["index", "nifty", "sensex"],
    "etf": ["etf", "bees"],
    "bees": ["etf", "bees"],

    # Plan and option words, so "growth plan" is not treated as a company.
    "direct": ["direct"],
    "regular": ["regular"],
    "growth": ["growth"],
    "dividend": ["idcw", "dividend"],
    "idcw": ["idcw", "dividend"],
    "payout": ["idcw", "dividend"],

    # Houses whose everyday name differs from the registered one.
    "birla": ["aditya birla"],
    "icici": ["icici prudential"],
    "kotak": ["kotak mahindra", "kotak"],
    "hdfc": ["hdfc"],
    "sbi": ["sbi"],
}

# Words that say what kind of thing somebody is holding rather than which
# one. Left in, "reliance shares" asks for a company with "shares" in its
# name. "fund" is deliberately absent: for a scheme it is part of the name.
NOISE = {"my", "a", "an", "the", "of", "and", "in", "for", "share", "shares",
         "stock", "stocks", "holding", "holdings", "ltd", "limited", "lim",
         "co", "company", "inc", "plc", "some", "please", "find", "want"}

# How many concepts one query may carry. Past this it is a sentence, not a
# search, and every extra concept is another branch in the WHERE clause.
MAX_CONCEPTS = 6


def concepts(raw):
    """The query as a list of concepts, each a list of ways to write it.

    A concept is one idea somebody typed. "sbi bluechip" is two: SBI, and
    the thing they call blue chip, which the data calls large cap. Each
    comes back as every spelling worth matching:

        [["sbi"], ["blue chip", "bluechip", "large cap"]]

    A row matching any spelling of a concept has matched that concept once,
    which is what keeps the ranking honest -- offering three spellings of
    one word must not outrank a row that genuinely matched three different
    words.

    Noise words are dropped, unless dropping them would leave nothing.
    """
    cleaned = "".join(c if c.isalnum() or c in "&.-" else " "
                      for c in (raw or "").lower())
    words = cleaned.split()
    if not words:
        return []

    # Two-word aliases first, so "blue chip" is read as one concept before
    # "blue" and "chip" are considered separately.
    found = []
    index = 0
    while index < len(words) and len(found) < MAX_CONCEPTS:
        pair = " ".join(words[index:index + 2])
        if len(words) - index >= 2 and pair in ALIASES:
            found.append(_spellings(pair))
            index += 2
            continue

        word = words[index]
        index += 1
        if word in NOISE:
            continue
        found.append(_spellings(word))

    # Everything was noise -- somebody searching for "the company" gets the
    # words back rather than an empty search.
    if not found:
        found = [_spellings(w) for w in words[:MAX_CONCEPTS]]
    return found


def _spellings(word):
    """Every way one concept is written, the typed form always included."""
    out = [word]
    split = COMPOUNDS.get(word)
    if split:
        out.append(split)
    for alias in ALIASES.get(word, []):
        if alias not in out:
            out.append(alias)
    if split:
        for alias in ALIASES.get(split, []):
            if alias not in out:
                out.append(alias)
    return out
