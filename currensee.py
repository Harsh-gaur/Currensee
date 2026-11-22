"""Currensee - a transparent currency-exchange decision prototype.

The program has four independent engines:
* timing: a seven-day range, trend, and risk label from daily rates;
* providers: ranks supplied fee/spread offers by money received;
* routing: finds the best fee-adjusted conversion route;
* arbitrage: detects fee-adjusted negative cycles using Bellman-Ford.

It is an educational project.  It uses reference rates, not executable quotes,
and it must not be used as a trading recommendation.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable


API_ROOT = "https://api.frankfurter.dev/v2"


@dataclass(frozen=True)
class Provider:
    """A provider's cost expressed in the source currency."""

    name: str
    percentage_fee: float = 0.0
    spread: float = 0.0
    fixed_fee: float = 0.0


@dataclass(frozen=True)
class ProviderResult:
    provider: Provider
    received: float
    effective_rate: float
    extra_cost_percent: float


@dataclass(frozen=True)
class Forecast:
    current: float
    average_30d: float
    low_7d: float
    expected_7d: float
    high_7d: float
    momentum_percent: float
    daily_volatility_percent: float
    risk: str
    recommendation: str
    rationale: str


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        raise ValueError("At least one rate is required.")
    return statistics.fmean(values)


def timing_forecast(history: list[float]) -> Forecast:
    """Create an honest range forecast from at least 10 ordered observations."""
    if len(history) < 10 or any(rate <= 0 for rate in history):
        raise ValueError("Provide at least 10 positive daily rates.")

    current = history[-1]
    window = history[-30:]
    average = _mean(window)
    changes = [history[i] / history[i - 1] - 1 for i in range(1, len(history))]
    daily_vol = statistics.pstdev(changes) if len(changes) > 1 else 0.0
    momentum = current / average - 1
    # A wide-enough range communicates uncertainty instead of promising a price.
    seven_day_band = max(0.005, daily_vol * math.sqrt(7) * 1.5)
    expected = current * (1 + momentum * 0.20)
    low, high = expected * (1 - seven_day_band), expected * (1 + seven_day_band)
    annualised_vol = daily_vol * math.sqrt(252)
    risk = "Low" if annualised_vol < 0.06 else "Medium" if annualised_vol < 0.14 else "High"

    if current > average * 1.003 and momentum > 0:
        recommendation = "WAIT"
        rationale = "The current rate is above its 30-day average; waiting may improve the exchange rate."
    elif current < average * 0.997 or momentum < -0.01:
        recommendation = "EXCHANGE NOW"
        rationale = "The rate is below its recent average or losing momentum; delaying adds downside risk."
    else:
        recommendation = "EXCHANGE PARTIALLY"
        rationale = "The rate is close to its recent average; splitting the exchange reduces timing risk."

    return Forecast(
        current=current,
        average_30d=average,
        low_7d=low,
        expected_7d=expected,
        high_7d=high,
        momentum_percent=momentum * 100,
        daily_volatility_percent=daily_vol * 100,
        risk=risk,
        recommendation=recommendation,
        rationale=rationale,
    )


def rank_providers(amount: float, market_rate: float, providers: list[Provider]) -> list[ProviderResult]:
    """Rank providers by destination currency received after all declared costs."""
    if amount <= 0 or market_rate <= 0:
        raise ValueError("Amount and market rate must be positive.")
    results: list[ProviderResult] = []
    gross = amount * market_rate
    for provider in providers:
        retained = amount - provider.fixed_fee
        cost_fraction = provider.percentage_fee + provider.spread
        if retained <= 0 or not 0 <= cost_fraction < 1:
            raise ValueError(f"Invalid costs for provider: {provider.name}")
        received = retained * market_rate * (1 - cost_fraction)
        results.append(
            ProviderResult(
                provider=provider,
                received=received,
                effective_rate=received / amount,
                extra_cost_percent=(1 - received / gross) * 100,
            )
        )
    return sorted(results, key=lambda result: result.received, reverse=True)


def effective_rate(raw_rate: float, fee: float) -> float:
    """Convert a market rate into the rate received after a proportional fee."""
    if raw_rate <= 0 or not 0 <= fee < 1:
        raise ValueError("Rates must be positive and fees must be between 0 and 1.")
    return raw_rate * (1 - fee)


def best_route(rates: dict[str, dict[str, float]], source: str, target: str, fee: float = 0.0) -> tuple[list[str], float]:
    """Find the highest-return simple route using Bellman-Ford on -log(rates)."""
    currencies = list(rates)
    if source not in rates or target not in rates:
        raise ValueError("Source and target must be present in the rates matrix.")
    distance = {currency: math.inf for currency in currencies}
    predecessor: dict[str, str | None] = {currency: None for currency in currencies}
    distance[source] = 0.0

    for _ in range(len(currencies) - 1):
        changed = False
        for current, destinations in rates.items():
            if math.isinf(distance[current]):
                continue
            for destination, raw_rate in destinations.items():
                if destination not in distance:
                    continue
                candidate = distance[current] - math.log(effective_rate(raw_rate, fee))
                if candidate < distance[destination] - 1e-12:
                    distance[destination] = candidate
                    predecessor[destination] = current
                    changed = True
        if not changed:
            break

    if math.isinf(distance[target]):
        raise ValueError(f"No route exists from {source} to {target}.")
    path = [target]
    while path[-1] != source:
        parent = predecessor[path[-1]]
        if parent is None:
            raise ValueError(f"No route exists from {source} to {target}.")
        path.append(parent)
    path.reverse()
    return path, math.exp(-distance[target])


def detect_arbitrage(rates: dict[str, dict[str, float]], fee: float = 0.0, margin: float = 0.001) -> list[str] | None:
    """Return one profitable cycle after fees, or None when no meaningful cycle exists.

    margin is a minimum profit fraction, e.g. 0.001 is 0.1%.  A virtual source
    (all initial distances are zero) lets the method find cycles in every
    connected component.
    """
    currencies = list(rates)
    distance = {currency: 0.0 for currency in currencies}
    predecessor: dict[str, str | None] = {currency: None for currency in currencies}
    updated: str | None = None

    for _ in range(len(currencies)):
        updated = None
        for current, destinations in rates.items():
            for destination, raw_rate in destinations.items():
                if destination not in distance:
                    continue
                weight = -math.log(effective_rate(raw_rate, fee))
                if distance[current] + weight < distance[destination] - math.log1p(margin):
                    distance[destination] = distance[current] + weight
                    predecessor[destination] = current
                    updated = destination
        if updated is None:
            return None

    assert updated is not None
    cycle_start = updated
    for _ in range(len(currencies)):
        parent = predecessor[cycle_start]
        if parent is None:
            return None
        cycle_start = parent

    backward_cycle = [cycle_start]
    cursor = predecessor[cycle_start]
    while cursor is not None and cursor != cycle_start and len(backward_cycle) <= len(currencies):
        backward_cycle.append(cursor)
        cursor = predecessor[cursor]
    if cursor != cycle_start:
        return None
    backward_cycle.append(cycle_start)
    return list(reversed(backward_cycle))


def demo_history() -> list[float]:
    """Deterministic USD/INR demo data, oldest to newest, for offline use."""
    values = []
    for day in range(45):
        base = 83.45 + day * 0.006
        wave = 0.20 * math.sin(day * 0.52) + 0.07 * math.sin(day * 1.31)
        values.append(round(base + wave, 4))
    values[-1] = 83.94
    return values


def demo_rates() -> dict[str, dict[str, float]]:
    """Build a consistent all-pairs matrix from destination units per USD."""
    per_usd = {"USD": 1.0, "EUR": 0.9200, "GBP": 0.7900, "INR": 83.9400, "JPY": 150.2000, "CAD": 1.3500, "AUD": 1.5200, "CHF": 0.8800, "CNY": 7.1800, "SGD": 1.3400, "HKD": 7.8200, "NZD": 1.6400, "SEK": 10.4500, "NOK": 10.6000, "DKK": 6.8600, "PLN": 3.9800, "CZK": 23.2000, "HUF": 360.0000, "MXN": 17.1000, "BRL": 5.0200, "ZAR": 18.1000, "AED": 3.6700, "SAR": 3.7500, "THB": 35.7000, "KRW": 1330.0000, "IDR": 15700.0000, "TRY": 32.1000}
    return {
        base: {quote: per_usd[quote] / per_usd[base] for quote in per_usd}
        for base in per_usd
    }


def fetch_live_market(base: str, quotes: list[str], days: int = 45) -> tuple[float, list[float], dict[str, dict[str, float]]]:
    """Fetch public Frankfurter reference rates; no API key is needed.

    The v2 response is parsed defensively because it may return either a list
    of rows or a wrapper containing rows.  Reference rates update periodically,
    so this endpoint is unsuitable for live trading.
    """
    base = base.upper()
    # Keep the first requested quote as the pair being advised on; sorting here
    # would accidentally turn USD/INR into USD/EUR whenever EUR is also needed
    # for route comparison.
    quotes = list(dict.fromkeys(quote.upper() for quote in quotes if quote.upper() != base))
    params = urllib.parse.urlencode({"base": base.lower(), "quotes": ",".join(quote.lower() for quote in quotes)})
    with urllib.request.urlopen(f"{API_ROOT}/rates?{params}", timeout=12) as response:
        latest_payload = json.load(response)
    latest_rows = latest_payload.get("rates", latest_payload) if isinstance(latest_payload, dict) else latest_payload
    latest_by_quote = {str(row["quote"]).upper(): float(row["rate"]) for row in latest_rows}
    if not quotes:
        raise ValueError("At least one destination currency is required.")
    target = quotes[0]
    if target not in latest_by_quote:
        raise ValueError(f"No live rate returned for {base}/{target}.")

    start = date.today() - timedelta(days=days * 2)  # leaves room for non-business days
    history_params = urllib.parse.urlencode({"base": base.lower(), "quotes": target.lower(), "from": start.isoformat()})
    with urllib.request.urlopen(f"{API_ROOT}/rates?{history_params}", timeout=12) as response:
        history_payload = json.load(response)
    history_rows = history_payload.get("rates", history_payload) if isinstance(history_payload, dict) else history_payload
    history = [float(row["rate"]) for row in history_rows if str(row.get("quote", "")).upper() == target]
    if len(history) < 10:
        raise ValueError("The live API did not return enough history for a forecast.")

    per_base = {base: 1.0, **latest_by_quote}
    matrix = {left: {right: per_base[right] / per_base[left] for right in per_base} for left in per_base}
    return latest_by_quote[target], history, matrix


def format_report(source: str, target: str, amount: float, forecast: Forecast, provider_results: list[ProviderResult], route: list[str], route_rate: float, arbitrage_cycle: list[str] | None) -> str:
    best = provider_results[0]
    lines = [
        "CURRENSEE - Currency Exchange Decision Report",
        "=" * 46,
        f"Pair: {source}/{target} | Amount: {amount:,.2f} {source}",
        "",
        f"TIMING ADVICE: {forecast.recommendation} ({forecast.risk} risk)",
        forecast.rationale,
        f"Current rate: {forecast.current:.4f} {target} per {source}",
        f"30-day average: {forecast.average_30d:.4f}",
        f"7-day range: {forecast.low_7d:.4f} to {forecast.high_7d:.4f} (expected {forecast.expected_7d:.4f})",
        f"Momentum: {forecast.momentum_percent:+.2f}% | Daily volatility: {forecast.daily_volatility_percent:.2f}%",
        "",
        "PROVIDER COMPARISON (after declared fees and spreads)",
    ]
    for index, result in enumerate(provider_results, start=1):
        tag = " <- best" if index == 1 else ""
        lines.append(f"{index}. {result.provider.name}: {result.received:,.2f} {target} | effective rate {result.effective_rate:.4f} | cost {result.extra_cost_percent:.2f}%{tag}")
    lines += [
        "",
        f"BEST ROUTE (0.10% per leg assumed): {' -> '.join(route)}",
        f"Route effective rate: {route_rate:.4f} {target} per {source} | Estimated received: {amount * route_rate:,.2f} {target}",
        "",
        "ARBITRAGE CHECK: " + (f"Potential fee-adjusted cycle: {' -> '.join(arbitrage_cycle)}" if arbitrage_cycle else "No fee-adjusted opportunity above the 0.10% margin."),
        "",
        "Educational prototype only. Reference rates and stated fees may differ from executable provider quotes.",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Currensee currency exchange and arbitrage prototype")
    parser.add_argument("--source", default="USD", help="currency being exchanged (default: USD)")
    parser.add_argument("--target", default="INR", help="currency being received (default: INR)")
    parser.add_argument("--amount", type=float, default=100.0, help="amount in source currency (default: 100)")
    parser.add_argument("--live", action="store_true", help="use Frankfurter public reference rates instead of offline demo data")
    parser.add_argument("--demo-arbitrage", action="store_true", help="inject an artificial cycle to demonstrate the detector")
    args = parser.parse_args()

    source, target = args.source.upper(), args.target.upper()
    if args.amount <= 0:
        parser.error("--amount must be positive")
    try:
        if args.live:
            market_rate, history, matrix = fetch_live_market(source, [target, "EUR", "GBP", "JPY"])
        else:
            matrix = demo_rates()
            if source not in matrix or target not in matrix:
                parser.error("Offline demo supports: USD, EUR, GBP, INR, JPY. Use --live for other currencies.")
            market_rate = matrix[source][target]
            history = demo_history() if (source, target) == ("USD", "INR") else [market_rate * (0.995 + 0.01 * math.sin(day / 3)) for day in range(45)]
        if args.demo_arbitrage:
            matrix["USD"]["EUR"] *= 1.02  # explicitly artificial, for demonstration only

        forecast = timing_forecast(history)
        providers = [
            Provider("Platform C", percentage_fee=0.0015, spread=0.0019),
            Provider("Exchange B", percentage_fee=0.0030, spread=0.0036),
            Provider("Bank A", percentage_fee=0.0070, spread=0.0070),
        ]
        provider_results = rank_providers(args.amount, market_rate, providers)
        route, route_rate = best_route(matrix, source, target, fee=0.001)
        cycle = detect_arbitrage(matrix, fee=0.001, margin=0.001)
        print(format_report(source, target, args.amount, forecast, provider_results, route, route_rate, cycle))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
