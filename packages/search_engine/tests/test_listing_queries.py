from __future__ import annotations

import unittest

from dossieragent_search_engine import build_listing_search_query


class ListingQueryTests(unittest.TestCase):
    def test_build_listing_search_query_uses_scalar_filters_and_pagination(self) -> None:
        query = build_listing_search_query(
            user_id="usr_demo",
            filters={
                "q": "metro balcon",
                "status": "recommended",
                "city": "Toulouse",
                "district": "Carmes",
                "max_price": 850,
                "min_surface": 35,
                "min_score": 80,
            },
            limit=10,
            offset=20,
        )

        self.assertEqual(query["from"], 20)
        self.assertEqual(query["size"], 10)
        bool_query = query["query"]["bool"]
        self.assertIn({"term": {"user_id": "usr_demo"}}, bool_query["filter"])
        self.assertIn({"term": {"status": "recommended"}}, bool_query["filter"])
        self.assertIn({"term": {"city": "Toulouse"}}, bool_query["filter"])
        self.assertIn({"range": {"price": {"lte": 850}}}, bool_query["filter"])
        self.assertIn({"range": {"surface": {"gte": 35}}}, bool_query["filter"])
        self.assertIn({"range": {"fit_score": {"gte": 80}}}, bool_query["filter"])
        self.assertEqual(bool_query["must"][0]["multi_match"]["query"], "metro balcon")


if __name__ == "__main__":
    unittest.main()
