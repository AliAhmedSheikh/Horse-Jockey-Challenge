import random
import re
from sqlalchemy.orm import Session
from models import Price

MIN_PRICE = 1.50


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
    if not all_positions:
        return base
    count = sum(1 for p in all_positions if p == pos)
    if count > 1:
        total = sum({1: 3, 2: 2, 3: 1}.get(pos + i, 0) for i in range(count))
        return total / count
    return base


def normalise_name(name: str) -> str:
    n = name.lower().strip()
    n = re.sub(r"[^a-z0-9\s]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def names_match(a: str, b: str) -> bool:
    na = normalise_name(a)
    nb = normalise_name(b)
    if na == nb:
        return True
    wa = set(na.split())
    wb = set(nb.split())
    if len(wa & wb) >= min(len(wa), len(wb), 2):
        return True
    return False


def compute_value_rating(bookmaker_price: float, ai_price: float) -> str:
    if bookmaker_price == 0 or ai_price == 0:
        return "Neutral"
    overlay = (bookmaker_price - ai_price) / ai_price * 100
    if overlay > 15:
        return "Strong Value"
    elif overlay > 5:
        return "Value"
    elif overlay > -5:
        return "Neutral"
    else:
        return "Avoid"


def compute_status(bookmaker_price: float, ai_price: float) -> str:
    rating = compute_value_rating(bookmaker_price, ai_price)
    if rating in ("Strong Value", "Value"):
        return "value"
    elif rating == "Neutral":
        return "neutral"
    else:
        return "avoid"
