"""Offline behavioral checks for selected-page inspection and catalog integrity."""
import importlib.util
import base64
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("card_tools", Path(__file__).with_name("domo-card-tools.py"))
cards = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cards)


def definition():
    return {"urn": "123", "ownerId": "private-owner", "columns": [{"name": "private-column"}],
            "definition": {"chartVersion": 12,
                "charts": {"main": {"chartType": "badge_vert_bar", "overrides": {
                    "title_x": "private-axis", "hover_text": "private-tooltip"}}},
                "subscriptions": {"main": {"columns": [
                    {"column": "private-column", "mapping": "ITEM"},
                    {"column": "private-column", "mapping": "VALUE", "aggregation": "SUM",
                     "formulaId": "private-formula-id"}],
                    "filters": [{"values": ["private-filter-value"]}],
                    "groupBy": [{"column": "private-column"}], "orderBy": []}},
                "formulas": [{"formula": "private-expression"}],
                "dynamicTitle": {"text": "private-title"},
                "annotations": [{"content": "private-annotation"}]}}


class FakeClient:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def request(self, path, body=None):
        self.calls.append((path, body))
        if body is None:
            return [{"urn": "123", "type": "kpi", "title": "private-title"},
                    {"urn": "321", "type": "document"}]
        if self.fail:
            raise RuntimeError("private response body")
        return definition()


class CardTools(unittest.TestCase):
    def test_named_render_parts_validate_without_exposing_rows(self):
        raw = {"image": {"data": base64.b64encode(b"\x89PNG\r\n\x1a\nexample").decode()},
               "queryResult": {"limited": False, "data": {
                   "datasource": "private-dataset", "numRows": 1,
                   "rows": [["private-customer"]], "metadata": [{"type": "STRING"}]}},
               "limited": False, "notAllDataShown": False}
        result = cards.summarize_render(raw, "private-dataset")
        self.assertEqual(result["returned_rows"], 1)
        self.assertEqual(result["column_types"], ["STRING"])
        self.assertTrue(result["expected_dataset_checked"])
        self.assertNotIn("private", json.dumps(result))
        with self.assertRaises(ValueError):
            cards.summarize_render(raw, "wrong-dataset")
        raw["queryResult"]["data"]["numRows"] = 2
        with self.assertRaises(ValueError):
            cards.summarize_render(raw)

    def test_render_does_not_accept_positional_parts_or_non_png_data(self):
        for raw in ({"data": ["image"]}, {"image": {"data": "not base64"}},
                    {"image": {"data": base64.b64encode(b"not a PNG").decode()}}):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                cards.summarize_render(raw)

    def test_render_client_requires_both_dimensions_and_never_saves(self):
        with patch.dict(os.environ, {"INSTANCE": "example.domo.com", "SID": "synthetic"}, clear=True):
            client = cards.Client("example.domo.com")
            path = "/api/content/v1/cards/kpi/dr:456:123/render?parts=image,queryResult"
            with patch.object(cards, "urlopen") as network:
                for body in ({"width": 900}, {"height": 600}, {"width": 0, "height": 600},
                             {"width": 900, "height": 9000}, {"width": True, "height": 600},
                             {"width": 900, "height": 600, "definition": {}}):
                    with self.subTest(body=body), self.assertRaises(ValueError):
                        client.request(path, body)
                network.assert_not_called()

    def test_definition_drillpath_counts_ancestors_only(self):
        raw = definition()
        raw["drillpath"] = ["private-root", "private-parent"]
        report = cards.summarize_definition(raw)
        self.assertEqual(report["drill_ancestor_count"], 2)
        self.assertNotIn("private", json.dumps(report))

    def test_structural_report_does_not_leak_source_content(self):
        result = cards.summarize_definition(definition())
        self.assertNotIn("private-", json.dumps(result))
        self.assertEqual(result["subscriptions"]["main"]["roles"], {"ITEM": 1, "VALUE": 1})
        self.assertEqual(result["subscriptions"]["main"]["formula_reference_count"], 1)
        self.assertEqual(result["subscriptions"]["main"]["filter_count"], 1)
        self.assertNotIn("big_number", result["subscriptions"])

    def test_unrecognized_mapping_and_aggregation_are_not_echoed(self):
        raw = definition()
        raw["definition"]["subscriptions"]["main"]["columns"] = [
            {"mapping": "private-role", "aggregation": "private-expression"}]
        result = cards.summarize_definition(raw)
        self.assertNotIn("private-", json.dumps(result))
        self.assertEqual(result["subscriptions"]["main"]["roles"], {"UNMAPPED_OR_OTHER": 1})

    def test_missing_graph_is_an_error_instead_of_an_empty_success(self):
        for raw in ([], {}, {"definition": {}}, {"definition": {"charts": {"main": {"chartType": "domoapp"}}}}):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                cards.summarize_definition(raw)

    def test_page_scope_deduplicates_and_skips_non_kpis(self):
        client = FakeClient()
        report = cards.inspect(client, ["11", "11", "22"], ["123"])
        self.assertEqual(len(report["cards"]), 1)
        self.assertEqual(len(report["pages"]), 2)
        self.assertEqual(report["pages"][0]["other"], 1)
        self.assertEqual(client.calls, [
            ("/api/content/v1/pages/11/cards", None),
            ("/api/content/v1/pages/22/cards", None),
            ("/api/content/v3/cards/kpi/definition", {"dynamicText": True, "variables": True, "urn": "123"})])

    def test_failed_definition_is_counted_without_response_content(self):
        report = cards.inspect(FakeClient(fail=True), ["11"], [])
        self.assertEqual(len(report["failures"]), 1)
        self.assertEqual(report["cards"], [])
        self.assertNotIn("private", json.dumps(report))

    def test_page_url_must_match_host_and_expected_path(self):
        self.assertEqual(cards.page_id("https://example.domo.com/page/12", "example.domo.com"), "12")
        for url in ("https://other.domo.com/page/12", "https://example.domo.com@evil.invalid/page/12",
                    "http://example.domo.com/page/12", "https://example.domo.com/api/delete/12",
                    "https://example.domo.com/page/12?redirect=evil"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                cards.page_id(url, "example.domo.com")

    def test_client_does_not_send_unsupported_mutations(self):
        with patch.dict(os.environ, {"INSTANCE": "example.domo.com", "SID": "synthetic"}, clear=True):
            client = cards.Client("example.domo.com")
            with patch.object(cards, "urlopen") as network:
                for path, body in (("/api/content/v1/cards/123", {}),
                                   ("/api/content/v1/cards/123/copy", {}),
                                   ("/api/content/v3/cards/kpi/definition", {"urn": "123"})):
                    with self.subTest(path=path), self.assertRaises(ValueError):
                        client.request(path, body)
                network.assert_not_called()

    def test_credentials_cannot_silently_target_a_different_instance(self):
        with patch.dict(os.environ, {"INSTANCE": "other.domo.com", "SID": "synthetic"}, clear=True):
            with self.assertRaises(ValueError):
                cards.Client("example.domo.com")

    def test_per_chart_schema_variants_are_preserved(self):
        catalog = {"chart_types": {
            "badge_one": {"property_refs": ["x1"]}, "badge_two": {"property_refs": ["x2"]}},
            "properties": {"x1": {"key": "x", "label": "X", "category": "General", "valueList": ["A"]},
                           "x2": {"key": "x", "label": "X", "category": "General", "valueList": ["B"]}}}
        self.assertEqual(cards.lookup(catalog, "badge_two", "", "x")["property_schemas"][0]["valueList"], ["B"])

    def test_hex_evidence_does_not_rewrite_named_color_lists(self):
        catalog = json.loads(cards.CATALOG.read_text())
        props = cards.lookup(catalog, "badge_gauge", "", "range1_color")["property_schemas"]
        self.assertEqual(len(props), 1)
        self.assertIn("Purple", props[0]["valueList"])
        self.assertEqual(props[0]["live_hex_color_chart_types"], ["badge_gauge"])
        self.assertNotIn("documentation_ui_hex_picker", props[0])

    def test_catalog_has_no_dangling_refs_or_incorrect_coverage(self):
        catalog = json.loads(cards.CATALOG.read_text())
        types = catalog["chart_types"]
        self.assertEqual(len(types), catalog["totals"]["chart_types"])
        self.assertEqual(sum(c["live_card_count"] for c in types.values()), catalog["totals"]["cards"])
        authored = [c["later_authoring_validation"] for c in types.values()
                    if "later_authoring_validation" in c]
        self.assertEqual(len(authored), catalog["authoring_validation"]["final_chart_types"])
        self.assertEqual(sum(c["displayed_cards_saved_and_rendered"] for c in authored),
                         catalog["authoring_validation"]["displayed_cards"])
        for code, chart in types.items():
            with self.subTest(chart=code):
                self.assertTrue(chart["documented_columns"])
                for slot in chart["documented_columns"]:
                    raw = definition()
                    raw["definition"]["subscriptions"]["main"]["columns"] = [{"mapping": slot["name"]}]
                    summary = cards.summarize_definition(raw)
                    self.assertEqual(summary["subscriptions"]["main"]["roles"], {slot["name"]: 1})
                for ref in chart["property_refs"]:
                    self.assertIn(ref, catalog["properties"])
                self.assertEqual(sum(s["card_count"] for s in chart["observed_role_signatures"]),
                                 chart["live_card_count"])
        union = {k for c in types.values() for k in c["observed_override_keys"]}
        self.assertEqual(len(union), catalog["totals"]["observed_override_keys"])


if __name__ == "__main__":
    unittest.main()
