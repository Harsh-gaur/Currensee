"""Streamlit interface for the Currensee project."""

import math

import streamlit as st

from currensee import (
    Provider,
    best_route,
    demo_history,
    demo_rates,
    detect_arbitrage,
    fetch_live_market,
    rank_providers,
    timing_forecast,
)


st.set_page_config(page_title="Currensee", page_icon="💱", layout="wide")
st.title("💱 Currensee")
st.caption("Exchange smarter: timing, provider costs, routes, and arbitrage signals in one place.")

with st.sidebar:
    st.header("Exchange details")
    use_live = st.toggle("Use live reference rates", value=False)
    source = st.selectbox("You exchange", ["USD", "EUR", "GBP", "INR", "JPY"], index=0)
    target_choices = [currency for currency in ["USD", "EUR", "GBP", "INR", "JPY"] if currency != source]
    target = st.selectbox("You receive", target_choices, index=target_choices.index("INR") if "INR" in target_choices else 0)
    amount = st.number_input(f"Amount in {source}", min_value=1.0, value=100.0, step=10.0)
    st.caption("Live mode uses public reference data. It is not an executable exchange quote.")


@st.cache_data(ttl=3600, show_spinner=False)
def get_live_data(source_currency: str, target_currency: str):
    return fetch_live_market(source_currency, [target_currency, "EUR", "GBP", "JPY"])


try:
    if use_live:
        with st.spinner("Fetching public reference rates..."):
            market_rate, history, matrix = get_live_data(source, target)
    else:
        matrix = demo_rates()
        market_rate = matrix[source][target]
        history = demo_history() if (source, target) == ("USD", "INR") else [
            market_rate * (0.995 + 0.01 * math.sin(day / 3)) for day in range(45)
        ]

    forecast = timing_forecast(history)
    provider_results = rank_providers(
        amount,
        market_rate,
        [
            Provider("Platform C", percentage_fee=0.0015, spread=0.0019),
            Provider("Exchange B", percentage_fee=0.0030, spread=0.0036),
            Provider("Bank A", percentage_fee=0.0070, spread=0.0070),
        ],
    )
    route, route_rate = best_route(matrix, source, target, fee=0.001)
    arbitrage_cycle = detect_arbitrage(matrix, fee=0.001, margin=0.001)
except (OSError, ValueError, KeyError) as error:
    st.error(f"The data could not be analysed: {error}")
    st.stop()

left, middle, right = st.columns(3)
left.metric("Recommendation", forecast.recommendation)
middle.metric("Current reference rate", f"{forecast.current:.4f} {target}")
right.metric("Risk level", forecast.risk)
st.info(forecast.rationale)

st.subheader("When should I exchange?")
timing_left, timing_middle, timing_right = st.columns(3)
timing_left.metric("30-day average", f"{forecast.average_30d:.4f}")
timing_middle.metric("7-day estimated range", f"{forecast.low_7d:.4f} - {forecast.high_7d:.4f}")
timing_right.metric("Momentum", f"{forecast.momentum_percent:+.2f}%")

st.subheader("Where should I exchange?")
st.dataframe(
    [
        {
            "Provider": result.provider.name,
            f"You receive ({target})": round(result.received, 2),
            "Effective rate": round(result.effective_rate, 4),
            "Cost vs. mid-market": f"{result.extra_cost_percent:.2f}%",
        }
        for result in provider_results
    ],
    use_container_width=True,
    hide_index=True,
)

st.subheader("How should I exchange?")
route_col, cycle_col = st.columns(2)
route_col.success(f"Best fee-adjusted route: {' → '.join(route)}")
route_col.write(f"Estimated received: **{amount * route_rate:,.2f} {target}**")
if arbitrage_cycle:
    cycle_col.warning(f"Potential fee-adjusted cycle: {' → '.join(arbitrage_cycle)}")
else:
    cycle_col.info("No fee-adjusted arbitrage opportunity above the 0.10% margin.")

st.divider()
st.caption("Educational project only, not financial advice. Provider fees are illustrative and public reference rates can differ from an executable quote.")
