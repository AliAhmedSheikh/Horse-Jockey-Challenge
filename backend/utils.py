import random
import re
from sqlalchemy.orm import Session
from models import Price

MIN_PRICE = 1.50
MAX_PRICE = 100.0


def weighted_shuffle(participants, db: Session, meeting_id: str):
    shuffled = list(participants)
    pids = [p.id for p in shuffled]
    price_rows = db.query(Price).filter(
        Price.participant_id.in_(pids),
        Price.bookmaker_name == "Ladbrokes",
    ).all()
    price_map = {pr.participant_id: pr.price for pr in price_rows}
    weights = {}
    for p in shuffled:
        price = price_map.get(p.id, 3.0)
        weight = 1.0 / max(price, MIN_PRICE)
        weight *= random.uniform(0.6, 1.4)
        weights[p.id] = weight
    shuffled.sort(key=lambda p: weights[p.id], reverse=True)
    return shuffled


def race_points(pos, all_positions=None):
    if pos > 3:
        return 0
    base = {1: 3, 2: 2, 3: 1}[pos]
    if all_positions is None:
        return base
    count = sum(1 for p in all_positions if p == pos)
    if count > 1:
        total = sum({1: 3, 2: 2, 3: 1}.get(pos + i, 0) for i in range(count))
        return total / count
    return base


def normalise_name(name: str) -> str:
    n = name.lower().strip()
    n = n.replace("-", " ")
    n = re.sub(r"[^a-z0-9\s]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _strip_parens(name: str) -> str:
    return re.sub(r'\s*\([^)]*\)\s*', ' ', name).strip()


def _name_words(name: str) -> list:
    """Return normalised word list from a name, with hyphens split."""
    cleaned = _strip_parens(name)
    return normalise_name(cleaned).split()


def names_match(a: str, b: str) -> bool:
    if not a or not b:
        return False

    wa = _name_words(a)
    wb = _name_words(b)
    if not wa or not wb:
        return False

    # Exact match after normalisation
    if wa == wb:
        return True

    # Build word sets (handles reorder like "Green Egerton" == "Egerton Green")
    set_a = set(wa)
    set_b = set(wb)
    overlap = set_a & set_b

    # Require matching words to cover a meaningful portion of both names
    # At least 2 matching words AND at least 70% of the shorter name's words
    max_words = max(len(set_a), len(set_b))
    min_words = min(len(set_a), len(set_b))
    if min_words >= 2 and len(overlap) >= 2:
        # Require 70%+ of the shorter name to match
        if len(overlap) / min_words >= 0.70:
            # Also require overlap covers at least 75% of the longer name
            if len(overlap) / max_words >= 0.75:
                return True

    # Compound surname shorthand: if shorter name is a subset of longer name's words
    # AND shorter name doesn't contain the first word of the longer name,
    # it's likely a shorthand (e.g. "Egerton Green" for "Dylan Egerton-Green")
    if set_a.issubset(set_b) or set_b.issubset(set_a):
        shorter_words = wa if len(wa) <= len(wb) else wb
        longer_words = wb if len(wa) <= len(wb) else wa
        longer_first = longer_words[0]
        if longer_first not in shorter_words:
            # Shorter name doesn't contain first name of longer → shorthand
            return True

    # Handle hyphenated compound surnames: try concatenation variants
    # "EgertonGreen" should match "Egerton Green"
    full_a = "".join(wa)
    full_b = "".join(wb)
    if full_a == full_b:
        return True

    # Also check if removing spaces from one variant matches a hyphen variant
    no_space_a = "".join(wa)
    no_space_b = "".join(wb)
    if no_space_a == no_space_b:
        return True

    # Handle initials: "d egerton green" should match "dylan egerton green"
    def _expand_initials(words, all_other_words):
        expanded = set(words)
        for w in words:
            if len(w) == 1:
                for ow in all_other_words:
                    if ow.startswith(w) and len(ow) > 1:
                        expanded.add(ow)
        return expanded

    # Handle initials: "d egerton green" should match "dylan egerton green"
    # Only apply if one name actually has an initial (single-letter word)
    has_initial_a = any(len(w) == 1 for w in wa)
    has_initial_b = any(len(w) == 1 for w in wb)
    if has_initial_a or has_initial_b:
        exp_a = _expand_initials(wa, set_b)
        exp_b = _expand_initials(wb, set_a)
        overlap3 = exp_a & exp_b
        if len(overlap3) >= min(len(exp_a), len(exp_b), 2):
            return True

    # Compound surname with initials: "egerton-green d" should match "dylan egerton green"
    # Check if one set has compound parts that span multiple words in the other
    compound_a = "".join(sorted(wa))
    compound_b = "".join(sorted(wb))
    if compound_a == compound_b:
        return True

    # Last-name fallback: requires last name >= 5 chars AND at least one other word match
    # AND the shorter name must have >= 3 words (prevents "Dylan Green" matching "Dylan Egerton-Green")
    if wa[-1] == wb[-1] and len(wa[-1]) >= 5:
        other_overlap = (set_a - {wa[-1]}) & (set_b - {wb[-1]})
        if other_overlap and (min(len(wa), len(wb)) >= 3 or len(other_overlap) >= 2):
            return True

    return False


def names_lastname_fallback(a: str, b: str) -> bool:
    """Last-resort matching: check if last names match.
    Handles cases where API returns a different first-name variant."""
    a = re.sub(r'\s*\([^)]*\)\s*', ' ', a)
    b = re.sub(r'\s*\([^)]*\)\s*', ' ', b)
    na = normalise_name(a)
    nb = normalise_name(b)
    wa = na.split()
    wb = nb.split()
    if not wa or not wb:
        return False
    # Last name must be at least 3 chars to avoid false positives
    return len(wa[-1]) >= 3 and len(wb[-1]) >= 3 and wa[-1] == wb[-1]


def compute_value_rating(bookmaker_price: float, ai_price: float, strong_value_threshold: float = 15.0) -> str:
    if bookmaker_price <= 0 or ai_price <= 0:
        return "Neutral"
    overlay = (bookmaker_price - ai_price) / ai_price * 100
    if overlay > strong_value_threshold:
        return "Strong Value"
    elif overlay > 5:
        return "Value"
    elif overlay > -5:
        return "Neutral"
    else:
        return "Avoid"


def compute_status(bookmaker_price: float, ai_price: float, strong_value_threshold: float = 15.0) -> str:
    rating = compute_value_rating(bookmaker_price, ai_price, strong_value_threshold)
    if rating in ("Strong Value", "Value"):
        return "value"
    elif rating == "Neutral":
        return "neutral"
    else:
        return "avoid"
