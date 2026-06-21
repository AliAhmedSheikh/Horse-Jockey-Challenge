import random
import re
from sqlalchemy.orm import Session
from models import Price

MIN_PRICE = 1.50
MAX_PRICE = 100.0
POINTS_TABLE = {1: 3, 2: 2, 3: 1}

# Retained for scraper import compatibility (scrapers are disabled but still imported)
CHALLENGE_MARGINS = {
    "Ladbrokes": 0.0,
    "TAB": 0.04,
    "TABtouch": 0.02,
    "Sportsbet": 0.03,
    "PointsBet": -0.03,
}

CHALLENGE_STRATEGIES = {
    "Ladbrokes": "best",
    "TAB": "best",
    "TABtouch": "best",
    "Sportsbet": "best",
    "PointsBet": "best",
}


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
    base = POINTS_TABLE[pos]
    if all_positions is None:
        return base
    count = sum(1 for p in all_positions if p == pos)
    if count > 1:
        total = sum(POINTS_TABLE.get(pos + i, 0) for i in range(count))
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
    cleaned = _strip_parens(name)
    return normalise_name(cleaned).split()


def names_match(a: str, b: str) -> bool:
    if not a or not b:
        return False

    wa = _name_words(a)
    wb = _name_words(b)
    if not wa or not wb:
        return False

    if wa == wb:
        return True

    set_a = set(wa)
    set_b = set(wb)
    overlap = set_a & set_b

    max_words = max(len(set_a), len(set_b))
    min_words = min(len(set_a), len(set_b))
    if min_words >= 2 and len(overlap) >= 2:
        if len(overlap) / min_words >= 0.70:
            if len(overlap) / max_words >= 0.75:
                return True

    if set_a.issubset(set_b) or set_b.issubset(set_a):
        shorter_words = wa if len(wa) <= len(wb) else wb
        longer_words = wb if len(wa) <= len(wb) else wa
        longer_first = longer_words[0]
        if longer_first not in shorter_words:
            return True

    full_a = "".join(wa)
    full_b = "".join(wb)
    if full_a == full_b:
        return True

    no_space_a = "".join(wa)
    no_space_b = "".join(wb)
    if no_space_a == no_space_b:
        return True

    def _expand_initials(words, all_other_words):
        expanded = set(words)
        for w in words:
            if len(w) == 1:
                for ow in all_other_words:
                    if ow.startswith(w) and len(ow) > 1:
                        expanded.add(ow)
        return expanded

    has_initial_a = len(wa) > 0 and len(wa[0]) == 1
    has_initial_b = len(wb) > 0 and len(wb[0]) == 1
    if has_initial_a or has_initial_b:
        exp_a = _expand_initials(wa, set_b)
        exp_b = _expand_initials(wb, set_a)
        overlap3 = exp_a & exp_b
        if len(overlap3) >= min(len(exp_a), len(exp_b), 2):
            return True

    compound_a = "".join(sorted(wa))
    compound_b = "".join(sorted(wb))
    if compound_a == compound_b:
        return True

    if wa[-1] == wb[-1] and len(wa[-1]) >= 5:
        first_a, first_b = wa[0], wb[0]
        first_is_prefix = (
            (len(first_a) >= 3 and first_b.startswith(first_a))
            or (len(first_b) >= 3 and first_a.startswith(first_b))
        )
        first_match = (
            first_a == first_b
            or (len(first_a) == 1 and first_b.startswith(first_a))
            or (len(first_b) == 1 and first_a.startswith(first_b))
            or first_is_prefix
        )
        if not first_match:
            return False
        if first_is_prefix:
            return True
        meaningful_a = {w for w in set_a - {wa[-1]} if len(w) > 1}
        meaningful_b = {w for w in set_b - {wb[-1]} if len(w) > 1}
        other_overlap = meaningful_a & meaningful_b
        if other_overlap and (min(len(wa), len(wb)) >= 3 or len(other_overlap) >= 2):
            return True

    return False


def names_lastname_fallback(a: str, b: str) -> bool:
    a = re.sub(r'\s*\([^)]*\)\s*', ' ', a)
    b = re.sub(r'\s*\([^)]*\)\s*', ' ', b)
    na = normalise_name(a)
    nb = normalise_name(b)
    wa = na.split()
    wb = nb.split()
    if not wa or not wb:
        return False
    return len(wa[-1]) >= 3 and len(wb[-1]) >= 3 and wa[-1] == wb[-1]
