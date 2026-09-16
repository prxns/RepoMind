import unittest

from metrics import score


class MetricTests(unittest.TestCase):
    def test_source_level_metrics(self):
        result = score(["wrong.py", "right.py"], {"right.py"}, 2)
        self.assertEqual(result["recall_at_k"], 1.0)
        self.assertEqual(result["precision_at_k"], 0.5)
        self.assertEqual(result["mrr_at_k"], 0.5)
        self.assertGreater(result["ndcg_at_k"], 0)


if __name__ == "__main__":
    unittest.main()
