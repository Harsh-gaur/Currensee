import unittest

from currensee import Provider, best_route, demo_rates, detect_arbitrage, rank_providers, timing_forecast


class CurrenseeTests(unittest.TestCase):
    def test_provider_ranking_uses_all_costs(self):
        results = rank_providers(100, 80, [Provider("Costly", 0.01), Provider("Cheaper", 0.002, 0.001)])
        self.assertEqual(results[0].provider.name, "Cheaper")
        self.assertGreater(results[0].received, results[1].received)

    def test_best_route_returns_direct_pair_in_consistent_matrix(self):
        route, rate = best_route(demo_rates(), "USD", "INR", fee=0.0)
        self.assertEqual(route, ["USD", "INR"])
        self.assertAlmostEqual(rate, 83.94)

    def test_detector_finds_a_profitable_cycle(self):
        rates = {"USD": {"EUR": 1.0}, "EUR": {"GBP": 1.0}, "GBP": {"USD": 1.02}}
        cycle = detect_arbitrage(rates, margin=0.001)
        self.assertIsNotNone(cycle)
        self.assertEqual(cycle[0], cycle[-1])

    def test_forecast_requires_history(self):
        with self.assertRaises(ValueError):
            timing_forecast([1.0] * 9)


if __name__ == "__main__":
    unittest.main()
