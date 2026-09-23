"""Recommendation identity and seen-anime behavior with a simulated model."""

from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from tests import support  # noqa: F401
from services import recommender


class RecommenderServiceTests(unittest.TestCase):
    def setUp(self):
        self.model = MagicMock()
        self.spark = MagicMock()
        self.enterContext(patch.object(recommender, "_model", self.model))
        self.ensure_model = self.enterContext(
            patch.object(recommender, "_ensure_model", return_value=True)
        )
        self.get_spark = self.enterContext(
            patch.object(recommender, "_get_spark", return_value=self.spark)
        )

    def test_model_membership_does_not_assume_seen_history_means_a_trained_user(self):
        with patch.object(recommender, "_seen_items", {902: {1, 2}}):
            self.model.userFactors.filter.return_value.limit.return_value.count.return_value = 0
            self.assertFalse(recommender.has_trained_user(902))

        with patch.object(recommender, "_seen_items", {}):
            self.model.userFactors.filter.return_value.limit.return_value.count.return_value = 1
            self.assertTrue(recommender.has_trained_user(902))

    def test_unavailable_model_is_distinct_from_an_unknown_profile(self):
        self.ensure_model.return_value = False

        self.assertIsNone(recommender.has_trained_user(902))
        self.assertIsNone(recommender.generate_recommendations(902))

        self.get_spark.assert_not_called()
        self.model.userFactors.filter.assert_not_called()

    def test_heavily_reviewed_profile_receives_unseen_anime_with_titles(self):
        def model_results(users, candidate_count):
            result = MagicMock()
            result.collect.return_value = [
                SimpleNamespace(
                    recommendations=[
                        SimpleNamespace(movieId=anime_id, rating=8.5)
                        for anime_id in range(1, candidate_count + 1)
                    ]
                )
            ]
            return result

        self.model.recommendForUserSubset.side_effect = model_results
        with patch.object(recommender, "_seen_items", {902: set(range(1, 121))}):
            with patch("services.catalog.anime_titles", return_value={122: "Example Anime"}) as titles:
                result = recommender.generate_recommendations(902, 3)

        self.assertEqual([item["movieId"] for item in result], [121, 122, 123])
        self.assertEqual(result[1]["title"], "Example Anime")
        self.assertEqual(result[0]["title"], "Anime #121")
        titles.assert_called_once_with([121, 122, 123])
        self.spark.createDataFrame.assert_called_once_with([(902,)], ["userId"])

    def test_model_without_recommendations_returns_empty_results(self):
        self.model.recommendForUserSubset.return_value.collect.return_value = []

        with patch.object(recommender, "_seen_items", {}):
            self.assertEqual(recommender.generate_recommendations(902, 3), [])


if __name__ == "__main__":
    unittest.main()
