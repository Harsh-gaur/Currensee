# Currensee: Exchange Smarter, Not Harder

An offline-first Python prototype for a FinTech project. It turns the project brief into four explainable components:

- **When to exchange:** a 30-day average, momentum, volatility-based seven-day range, risk label, and `EXCHANGE NOW`, `EXCHANGE PARTIALLY`, or `WAIT` recommendation.
- **Where to exchange:** ranks providers by the destination amount after their stated percentage fee, spread, and fixed fee.
- **How to exchange:** converts the currency market into a graph and uses Bellman-Ford with `-log(rate)` edge weights to find the route with the highest fee-adjusted return.
- **Arbitrage check:** detects a negative cycle only if it exceeds a 0.10% margin after the assumed per-leg fee.

## Run it

No package installation or API key is needed for the offline demonstration.

```powershell
python currensee.py
python currensee.py --source EUR --target JPY --amount 500
python currensee.py --demo-arbitrage
```

To use public reference data from Frankfurter, which does not require an API key:

```powershell
python currensee.py --live --source USD --target INR --amount 100
```

Run the automated checks with:

```powershell
python -m unittest -v
```

## Project structure

```text
currensee.py       Application, algorithms, command-line interface, and demo data
app.py              Interactive Streamlit dashboard for deployment
requirements.txt    Cloud dependency list
test_currensee.py  Offline automated checks
README.md          Setup and project explanation
```

## Deploy as a website

1. Create a GitHub repository and upload every file in this folder.
2. Open [Streamlit Community Cloud](https://share.streamlit.io/) and connect GitHub.
3. Select the repository, the `main` branch, and `app.py` as the entry point.
4. Click **Deploy**. Streamlit will install the packages in `requirements.txt` and provide a `streamlit.app` share link.

The dashboard defaults to offline demo data. Visitors can enable **Use live reference rates** in the sidebar; this calls Frankfurter directly and needs no API key.

## Important limitations

The live endpoint provides periodically updated **reference** rates rather than executable trading quotes. Provider fees in the prototype are illustrative inputs and must be maintained from real provider disclosures. The forecast presents a range and risk label; it does not promise a future rate. Therefore, this project is for education and decision support, not financial advice or automated trading.

## How the arbitrage model works

For an exchange from `A` to `B`, the edge weight is:

```text
weight(A, B) = -log(market_rate(A, B) * (1 - fee))
```

Multiplying rates around a cycle becomes adding weights. A negative total means the conversion product is greater than one. The program requires an additional 0.10% margin to reduce false signals caused by rounding, fees, and stale reference data.
