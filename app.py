"""Interactive Streamlit dashboard for the Currensee project."""

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


CURRENCIES = {
    "USD": ("US Dollar", "United States / global"), "EUR": ("Euro", "Euro area"),
    "GBP": ("Pound Sterling", "United Kingdom"), "INR": ("Indian Rupee", "India"),
    "JPY": ("Japanese Yen", "Japan"), "CAD": ("Canadian Dollar", "Canada"),
    "AUD": ("Australian Dollar", "Australia"), "CHF": ("Swiss Franc", "Switzerland"),
    "CNY": ("Chinese Yuan", "China"), "SGD": ("Singapore Dollar", "Singapore"),
    "HKD": ("Hong Kong Dollar", "Hong Kong"), "NZD": ("New Zealand Dollar", "New Zealand"),
    "SEK": ("Swedish Krona", "Sweden"), "NOK": ("Norwegian Krone", "Norway"),
    "DKK": ("Danish Krone", "Denmark"), "PLN": ("Polish Zloty", "Poland"),
    "CZK": ("Czech Koruna", "Czech Republic"), "HUF": ("Hungarian Forint", "Hungary"),
    "MXN": ("Mexican Peso", "Mexico"), "BRL": ("Brazilian Real", "Brazil"),
    "ZAR": ("South African Rand", "South Africa"), "AED": ("UAE Dirham", "United Arab Emirates"),
    "SAR": ("Saudi Riyal", "Saudi Arabia"), "THB": ("Thai Baht", "Thailand"),
    "KRW": ("South Korean Won", "South Korea"), "IDR": ("Indonesian Rupiah", "Indonesia"),
    "TRY": ("Turkish Lira", "Turkey"),
}
CURRENCY_CODES = list(CURRENCIES)


def label(code: str) -> str:
    name, region = CURRENCIES[code]
    return f"{code} - {name} ({region})"


def pair_history(rate: float) -> list[float]:
    """Create deterministic offline history when live data is disabled."""
    return [rate * (0.995 + 0.009 * math.sin(day / 3) + 0.002 * math.sin(day / 1.3)) for day in range(45)]


@st.cache_data(ttl=3600, show_spinner=False)
def get_live_data(source_currency: str, target_currency: str):
    quotes = [target_currency] + [code for code in CURRENCY_CODES if code not in {source_currency, target_currency}]
    return fetch_live_market(source_currency, quotes)


st.set_page_config(page_title="Currensee | FX decision dashboard", page_icon="💱", layout="wide")
st.markdown(
    """<style>
    .block-container {padding-top: 2rem; padding-bottom: 2rem;}
    div[data-testid="stMetric"] {background: #f7f9fc; border-radius: 12px; padding: 1rem;}
    [data-testid="stSidebar"] {background: #f5f7fb;}
    </style>""",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.title("💱 Currensee")
    st.caption("Exchange smarter, not harder")
    st.divider()
    st.subheader("Your exchange")
    use_live = st.toggle("Use live reference rates", value=False, help="Uses Frankfurter public reference data. No API key is required.")
    source = st.selectbox("You exchange", CURRENCY_CODES, index=0, format_func=label)
    target_options = [code for code in CURRENCY_CODES if code != source]
    target = st.selectbox("You receive", target_options, index=target_options.index("INR") if "INR" in target_options else 0, format_func=label)
    amount = st.number_input(f"Amount in {source}", min_value=1.0, value=100.0, step=10.0)
    route_fee = st.slider("Estimated fee per route leg", 0.0, 1.0, 0.10, 0.05, format="%.2f%%") / 100
    st.divider()
    st.caption("Live rates are reference rates, not a guaranteed provider quote. Demo mode is illustrative and works offline.")

try:
    if use_live:
        with st.spinner("Fetching public reference rates and history..."):
            market_rate, history, matrix = get_live_data(source, target)
        data_label = "Live public reference data"
    else:
        matrix = demo_rates()
        market_rate = matrix[source][target]
        history = demo_history() if (source, target) == ("USD", "INR") else pair_history(market_rate)
        data_label = "Offline demonstration data"

    forecast = timing_forecast(history)
    providers = [
        Provider("Platform C", percentage_fee=0.0015, spread=0.0019),
        Provider("Exchange B", percentage_fee=0.0030, spread=0.0036),
        Provider("Bank A", percentage_fee=0.0070, spread=0.0070),
    ]
    provider_results = rank_providers(amount, market_rate, providers)
    route, route_rate = best_route(matrix, source, target, fee=route_fee)
    arbitrage_cycle = detect_arbitrage(matrix, fee=route_fee, margin=0.001)
except (OSError, ValueError, KeyError) as error:
    st.error(f"The data could not be analysed: {error}")
    st.info("Try the offline demonstration mode, or select another pair.")
    st.stop()

st.title("Currency exchange decision dashboard")
st.caption(f"{data_label} | {label(source)} → {label(target)}")

top_one, top_two, top_three, top_four = st.columns(4)
top_one.metric("You receive at mid-market", f"{amount * market_rate:,.2f} {target}")
top_two.metric("Current rate", f"{market_rate:,.4f} {target}")
top_three.metric("Timing guidance", forecast.recommendation)
top_four.metric("Risk level", forecast.risk)

overview_tab, timing_tab, providers_tab, routes_tab, learn_tab = st.tabs(
    ["Overview", "Rates & timing", "Provider comparison", "Route & arbitrage", "Learn"]
)

with overview_tab:
    primary, side = st.columns([1.55, 1])
    with primary:
        st.subheader("Your decision, explained")
        st.info(forecast.rationale)
        st.write(
            f"For **{amount:,.2f} {source}**, the estimated reference conversion is "
            f"**{amount * market_rate:,.2f} {target}**. The best listed provider is "
            f"**{provider_results[0].provider.name}**, estimated to deliver "
            f"**{provider_results[0].received:,.2f} {target}** after its declared charges."
        )
        st.subheader("Quick checklist")
        st.markdown(
            "- Compare the final amount you receive, not only the advertised rate.\n"
            "- Check provider fees and exchange spreads before paying.\n"
            "- Use the forecast as a risk-aware range, never as a price promise.\n"
            "- Confirm the final quote directly with your provider."
        )
    with side:
        st.subheader("Pair snapshot")
        st.metric("30-day average", f"{forecast.average_30d:,.4f}")
        st.metric("Momentum", f"{forecast.momentum_percent:+.2f}%")
        st.metric("7-day estimated range", f"{forecast.low_7d:,.4f} - {forecast.high_7d:,.4f}")

with timing_tab:
    st.subheader(f"{source}/{target} trend")
    st.caption("The line shows available history. The forecast range is a volatility-based estimate, not a guarantee.")
    chart_rows = [{"Day": index + 1, "Rate": rate, "30-day average": forecast.average_30d} for index, rate in enumerate(history[-30:])]
    st.line_chart(chart_rows, x="Day", y=["Rate", "30-day average"], use_container_width=True)
    a, b, c, d = st.columns(4)
    a.metric("Current", f"{forecast.current:,.4f}")
    b.metric("Expected", f"{forecast.expected_7d:,.4f}")
    c.metric("Low estimate", f"{forecast.low_7d:,.4f}")
    d.metric("High estimate", f"{forecast.high_7d:,.4f}")
    with st.expander("How the timing guidance works"):
        st.write("Currensee compares the current rate with its recent average, measures momentum, and builds a seven-day uncertainty range from daily volatility. A higher volatility creates a wider range and may raise the risk level.")

with providers_tab:
    st.subheader("Provider comparison after declared costs")
    st.caption("Sample fee structures for project demonstration. Replace them with current provider quotes before making an exchange.")
    st.dataframe(
        [{"Rank": index, "Provider": result.provider.name, f"You receive ({target})": round(result.received, 2), "Effective rate": round(result.effective_rate, 4), "Cost vs mid-market": f"{result.extra_cost_percent:.2f}%"} for index, result in enumerate(provider_results, start=1)],
        use_container_width=True,
        hide_index=True,
    )
    best = provider_results[0]
    st.success(f"Best listed option: {best.provider.name}. Estimated cost against the mid-market reference: {amount * market_rate - best.received:,.2f} {target}.")

with routes_tab:
    left, right = st.columns(2)
    with left:
        st.subheader("Cheapest conversion route")
        st.success(" → ".join(route))
        st.metric("Estimated route result", f"{amount * route_rate:,.2f} {target}")
        st.caption(f"This assumes a {route_fee * 100:.2f}% cost on each conversion leg.")
    with right:
        st.subheader("Arbitrage monitor")
        if arbitrage_cycle:
            st.warning(f"Potential fee-adjusted cycle: {' → '.join(arbitrage_cycle)}")
            st.caption("A potential signal needs manual verification; rates, fees, limits, and settlement delays can remove the apparent gain.")
        else:
            st.info("No fee-adjusted arbitrage opportunity above the 0.10% margin was detected.")
        st.caption("The route engine converts each rate to a -log edge weight and uses Bellman-Ford to search for a higher-return route or a negative cycle.")

with learn_tab:
    st.subheader("Currency explorer")
    guide_currency = st.selectbox("Choose a currency to learn about", CURRENCY_CODES, format_func=label, key="guide_currency")
    name, region = CURRENCIES[guide_currency]
    st.write(f"**{guide_currency}** is the **{name}**, associated with **{region}**.")
    guide_left, guide_right = st.columns(2)
    with guide_left:
        st.markdown("**What changes your exchange result?**\n\n- The market rate\n- The provider's spread\n- Percentage and fixed fees\n- Transfer method and settlement time\n- The provider's final quoted rate")
    with guide_right:
        st.markdown("**Key terms**\n\n- **Mid-market rate:** a benchmark between buy and sell prices.\n- **Spread:** a provider's markup included in the rate.\n- **Volatility:** how much a rate moves over time.\n- **Arbitrage:** a theoretical gain from a conversion cycle after all costs.")
    st.warning("Educational project only - not financial advice. Never rely on a forecast or reference rate as an executable offer.")

st.divider()
st.caption("Currensee combines timing, provider costs, conversion routes, and fee-adjusted arbitrage detection. Built for learning and project demonstration.")
