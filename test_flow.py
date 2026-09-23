import unittest
from test_smartspend import AppFlowTests, NlpTests


def run_tests():
    suite = unittest.TestSuite()
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(NlpTests))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(AppFlowTests))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    print("All SmartSpend flow tests passed.")


if __name__ == "__main__":
    run_tests()
