"""
加密货币K线分析节点 - 单元测试
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'Nodes'))

import unittest
from crypto_klines_utils import (
    calculate_atr_avg,
    calculate_std_dev,
    safe_divide,
    format_float,
    wilder_smooth
)


class TestATRCalculation(unittest.TestCase):

    def test_normal(self):
        atr = [10.0, 12.0, 11.0, 13.0, 12.5]
        avg = calculate_atr_avg(atr, period=3)
        self.assertAlmostEqual(avg, (11.0 + 13.0 + 12.5) / 3, places=2)

    def test_with_none(self):
        atr = [10.0, None, 12.0, 13.0, 12.5]
        self.assertGreater(calculate_atr_avg(atr, period=3), 0)

    def test_insufficient_data(self):
        self.assertEqual(calculate_atr_avg([10.0, 12.0], period=5), 0.0)

    def test_empty(self):
        self.assertEqual(calculate_atr_avg([], period=3), 0.0)

    def test_all_none(self):
        self.assertEqual(calculate_atr_avg([None] * 20, period=10), 0.0)


class TestSafeDivide(unittest.TestCase):

    def test_normal(self):
        self.assertEqual(safe_divide(10, 2), 5.0)

    def test_zero(self):
        self.assertEqual(safe_divide(10, 0), 0.0)

    def test_zero_with_default(self):
        self.assertEqual(safe_divide(10, 0, default=999), 999)


class TestFormatFloat(unittest.TestCase):

    def test_normal(self):
        self.assertEqual(format_float(3.14159, 2), 3.14)

    def test_none(self):
        self.assertIsNone(format_float(None, 2))

    def test_zero_decimals(self):
        self.assertEqual(format_float(3.7, 0), 4.0)


class TestWilderSmooth(unittest.TestCase):

    def test_normal(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = wilder_smooth(data, 3)
        self.assertIsNone(result[0])
        self.assertIsNone(result[1])
        self.assertAlmostEqual(result[2], 2.0)
        self.assertIsNotNone(result[3])
        self.assertIsNotNone(result[4])

    def test_insufficient(self):
        result = wilder_smooth([1.0, 2.0], 5)
        self.assertTrue(all(v is None for v in result))


class TestStdDev(unittest.TestCase):

    def test_normal(self):
        data = [2, 4, 4, 4, 5, 5, 7, 9]
        mean = sum(data) / len(data)
        self.assertAlmostEqual(calculate_std_dev(data, mean), 2.0, places=1)

    def test_empty(self):
        self.assertEqual(calculate_std_dev([], 0), 0.0)


class TestSignalsImport(unittest.TestCase):
    """验证信号模块接口"""

    def test_generate_signals_import(self):
        from crypto_klines_signals import generate_signals
        self.assertTrue(callable(generate_signals))

    def test_generate_signals_insufficient_data(self):
        from crypto_klines_signals import generate_signals
        result = generate_signals(
            closes=[100.0],
            DIF=[None], DEA=[None], histogram=[None],
            rsi=[None], ema9=[None], ema21=[None],
            adx=[None], atr=[None],
            market_regime={"regime": "INSUFFICIENT_DATA", "confidence": 0}
        )
        self.assertEqual(result["overall_signal"], "INSUFFICIENT_DATA")
        self.assertEqual(result["signal_score"], 0)
        self.assertIn("trend", result["scores"])
        self.assertIn("momentum", result["scores"])
        self.assertIn("overall", result["scores"])

    def test_generate_signals_flat_data(self):
        from crypto_klines_signals import generate_signals
        n = 60
        result = generate_signals(
            closes=[100.0] * n,
            DIF=[0.0] * n, DEA=[0.0] * n, histogram=[0.0] * n,
            rsi=[50.0] * n, ema9=[100.0] * n, ema21=[100.0] * n,
            adx=[15.0] * n, atr=[5.0] * n,
            market_regime={"regime": "RANGING", "confidence": 0.7}
        )
        self.assertEqual(result["overall_signal"], "NEUTRAL")
        self.assertIn("details", result)
        self.assertIn("macd_cross", result["details"])
        self.assertIn("rsi_zone", result["details"])
        self.assertIn("trend_alignment", result["details"])


class TestModuleImports(unittest.TestCase):
    """验证所有模块可正常导入"""

    def test_klines_import(self):
        from Crypto_Klines import Inputs, Outputs, run_node
        self.assertEqual(len(Inputs), 3)
        self.assertEqual(Inputs[2]["Num"], 60)
        self.assertTrue(callable(run_node))

    def test_quant_report_import(self):
        from Crypto_QuantReport import run_node
        self.assertTrue(callable(run_node))


def run_tests():
    print("=" * 70)
    print("Running Crypto Klines Unit Tests")
    print("=" * 70)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestATRCalculation))
    suite.addTests(loader.loadTestsFromTestCase(TestSafeDivide))
    suite.addTests(loader.loadTestsFromTestCase(TestFormatFloat))
    suite.addTests(loader.loadTestsFromTestCase(TestWilderSmooth))
    suite.addTests(loader.loadTestsFromTestCase(TestStdDev))
    suite.addTests(loader.loadTestsFromTestCase(TestSignalsImport))
    suite.addTests(loader.loadTestsFromTestCase(TestModuleImports))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 70)
    print(f"Tests completed: {result.testsRun}")
    print(f"Success: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("=" * 70)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
