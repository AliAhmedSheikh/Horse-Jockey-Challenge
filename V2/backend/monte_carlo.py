"""
Monte Carlo Simulation Engine for Jockey/Driver Challenge Pre-Match Pricing.

Uses Harville Formula for 2nd/3rd place probabilities and simulates
10,000 complete race meetings to calculate challenge win probabilities.
"""
import json
import math
import random
from collections import defaultdict
from typing import Dict, List, Tuple, Optional


def _strip_overround(horses: List[Dict]) -> List[Dict]:
    """Strip bookmaker margin from odds to get true win probabilities.

    Each horse dict must have 'odds' key.
    Returns same list with 'true_prob' added to each horse.
    """
    total_implied = sum(1.0 / h["odds"] for h in horses if h["odds"] > 0)
    if total_implied <= 0:
        for h in horses:
            h["true_prob"] = 0.0
        return horses
    for h in horses:
        if h["odds"] > 0:
            h["true_prob"] = (1.0 / h["odds"]) / total_implied
        else:
            h["true_prob"] = 0.0
    return horses


def _harville_second(winners_remaining: List[Dict], winner_idx: int) -> List[float]:
    """Calculate P(2nd = j | 1st = winner) using Harville Formula.

    P(j finishes 2nd | i won) = P_j / (1 - P_i)
    """
    winner_prob = winners_remaining[winner_idx]["true_prob"]
    denom = 1.0 - winner_prob
    if denom <= 0:
        n = len(winners_remaining)
        return [1.0 / n if n > 0 else 0.0] * n
    probs = []
    for i, h in enumerate(winners_remaining):
        if i == winner_idx:
            probs.append(0.0)
        else:
            probs.append(h["true_prob"] / denom)
    total = sum(probs)
    if total > 0:
        probs = [p / total for p in probs]
    return probs


def _harville_third(winners_remaining: List[Dict], winner_idx: int, second_idx: int) -> List[float]:
    """Calculate P(3rd = k | 1st=i, 2nd=j) using Harville Formula.

    P(k finishes 3rd | i won, j 2nd) = P_k / (1 - P_i - P_j)
    """
    wp = winners_remaining[winner_idx]["true_prob"]
    sp = winners_remaining[second_idx]["true_prob"]
    denom = 1.0 - wp - sp
    if denom <= 0:
        n = len(winners_remaining)
        return [1.0 / n if n > 0 else 0.0] * n
    probs = []
    for i, h in enumerate(winners_remaining):
        if i == winner_idx or i == second_idx:
            probs.append(0.0)
        else:
            probs.append(h["true_prob"] / denom)
    total = sum(probs)
    if total > 0:
        probs = [p / total for p in probs]
    return probs


def _weighted_choice(items: List, weights: List[float], rng: random.Random) -> any:
    """Choose an item from a list using weights."""
    total = sum(weights)
    if total <= 0:
        return rng.choice(items)
    r = rng.random() * total
    cumulative = 0.0
    for item, w in zip(items, weights):
        cumulative += w
        if r <= cumulative:
            return item
    return items[-1]


def simulate_race(
    race_runners: List[Dict],
    rng: random.Random,
) -> Tuple[Optional[Dict], Optional[Dict], Optional[Dict]]:
    """Simulate a single race using Harville Formula.

    Args:
        race_runners: list of dicts with 'jockey', 'horse', 'odds', 'true_prob'
        rng: random generator

    Returns:
        (winner, second, third) runner dicts (or None if not enough runners)
    """
    if len(race_runners) < 1:
        return None, None, None

    # Step 1: Pick winner based on true probabilities
    winner_idx = _weighted_choice(
        list(range(len(race_runners))),
        [r["true_prob"] for r in race_runners],
        rng,
    )

    # Step 2: Pick 2nd using Harville
    second_probs = _harville_second(race_runners, winner_idx)
    second_idx = _weighted_choice(
        list(range(len(race_runners))),
        second_probs,
        rng,
    )

    # Step 3: Pick 3rd using Harville
    third_probs = _harville_third(race_runners, winner_idx, second_idx)
    third_idx = _weighted_choice(
        list(range(len(race_runners))),
        third_probs,
        rng,
    )

    return race_runners[winner_idx], race_runners[second_idx], race_runners[third_idx]


def build_race_data_from_participants(
    participants: List[Dict],
    total_races: int,
) -> Dict[int, List[Dict]]:
    """Build per-race runner lists from participant race_odds_json data.

    Each participant has race_odds like:
      {"1": {"odds": 5.50, "horse": "Horse A"}, "3": {"odds": 12.0, "horse": "Horse B"}}

    Returns dict mapping race_number -> list of runner dicts.
    """
    races = {}
    for race_num in range(1, total_races + 1):
        runners = []
        for p in participants:
            race_odds = p.get("race_odds", {})
            race_key = str(race_num)
            if race_key in race_odds:
                rd = race_odds[race_key]
                odds = rd.get("odds", 0)
                horse = rd.get("horse", "")
                if odds > 0 and horse:
                    runners.append({
                        "jockey": p["name"],
                        "horse": horse,
                        "odds": float(odds),
                        "true_prob": 0.0,  # filled by _strip_overround
                    })
        if runners:
            _strip_overround(runners)
            races[race_num] = runners
    return races


def run_simulation(
    race_data: Dict[int, List[Dict]],
    total_races: int,
    n_simulations: int = 10000,
    seed: int = 42,
) -> Dict[str, float]:
    """Run Monte Carlo simulation for the full challenge.

    Args:
        race_data: dict mapping race_number -> list of runner dicts (with true_prob)
        total_races: total number of races in the meeting
        n_simulations: number of simulation runs
        seed: random seed for reproducibility

    Returns:
        dict mapping jockey name -> win probability (0.0 to 1.0)
    """
    rng = random.Random(seed)

    # Track how many times each jockey wins the challenge
    win_counts: Dict[str, float] = defaultdict(float)

    for _ in range(n_simulations):
        # Track points for each jockey this simulation
        jockey_points: Dict[str, float] = defaultdict(float)

        for race_num in range(1, total_races + 1):
            runners = race_data.get(race_num, [])
            if len(runners) < 3:
                continue

            winner, second, third = simulate_race(runners, rng)

            if winner:
                jockey_points[winner["jockey"]] += 3.0
            if second:
                jockey_points[second["jockey"]] += 2.0
            if third:
                jockey_points[third["jockey"]] += 1.0

        if not jockey_points:
            continue

        # Find the max points
        max_pts = max(jockey_points.values())

        # Find all jockeys tied at max
        winners = [j for j, pts in jockey_points.items() if abs(pts - max_pts) < 0.01]

        # Split the win equally among tied jockeys (dead-heat rule)
        share = 1.0 / len(winners)
        for j in winners:
            win_counts[j] += share

    # Convert counts to probabilities
    total_wins = sum(win_counts.values())
    if total_wins <= 0:
        return {}

    return {j: count / total_wins for j, count in win_counts.items()}


def calibrate_prob(raw_prob: float, power: float = 0.50, min_floor: float = 0.001) -> float:
    """Calibrate Monte Carlo win probability to bookmaker-style challenge price.

    Monte Carlo simulation gives the true probability of winning the challenge,
    but in a large field even the strongest favourite rarely exceeds 25-30%.
    This function compresses the probability range using a power transform so that
    prices match bookmaker-style challenge market conventions.

    With power=0.50:
      50% MC win prob → 70.7% effective → $1.41 (clamped to $1.50)
      30% → 54.8% → $1.83
      20% → 44.7% → $2.24
      10% → 31.6% → $3.16
       5% → 22.4% → $4.47
       1% → 10.0% → $10.00
     0.1% → 3.2% → $31.62
    0.01% → 1.0% → $100.0
    """
    p = max(min_floor, min(0.99, raw_prob))
    return p ** power


def _race_quality_price(p_data, total_races):
    """Compute fallback price from individual race odds quality."""
    race_odds = p_data.get("race_odds", {})
    if not race_odds:
        return 100.0
    total_race_prob = 0.0
    n_rides = 0
    for rn, rd in race_odds.items():
        if isinstance(rd, dict) and "odds" in rd and "horse" in rd:
            if rd["odds"] > 0 and rd["horse"]:
                n_rides += 1
                implied = 1.0 / rd["odds"]
                total_race_prob += implied
    if n_rides == 0:
        return 100.0
    rides_ratio = n_rides / max(total_races, 1)
    avg_race_prob = total_race_prob / n_rides if n_rides > 0 else 0
    est_challenge_prob = avg_race_prob * rides_ratio  # removed 0.6 multiplier
    if est_challenge_prob <= 0:
        return 100.0
    cal_prob = calibrate_prob(est_challenge_prob)
    return round(max(1.50, min(100.0, 1.0 / cal_prob)), 2)


def compute_challenge_prices(
    participants: List[Dict],
    total_races: int,
    n_simulations: int = 50000,
) -> Dict[str, float]:
    """Compute AI prices for all participants using Monte Carlo simulation.

    Uses calibrated probability to produce bookmaker-style challenge prices.
    """
    race_data = build_race_data_from_participants(participants, total_races)

    if not race_data:
        return {}

    win_probs = run_simulation(race_data, total_races, n_simulations)

    prices = {}
    for p in participants:
        name = p["name"]
        raw_prob = win_probs.get(name, 0.0)
        if raw_prob <= 0:
            prices[name] = _race_quality_price(p, total_races)
        else:
            cal_prob = calibrate_prob(raw_prob)
            price = 1.0 / cal_prob
            prices[name] = round(max(1.50, min(100.0, price)), 2)

    return prices
