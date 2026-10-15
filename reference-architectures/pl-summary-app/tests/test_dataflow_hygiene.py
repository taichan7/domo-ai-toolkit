import copy
import importlib.util
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("polish_dataflow", ROOT / "scripts/polish_dataflow.py")
polish = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(polish)


class DataflowHygiene(unittest.TestCase):
    def setUp(self):
        self.before = json.loads((ROOT / "dataflow/2042.json").read_text())

    def test_all_tiles_are_documented_sectioned_and_flow_left_to_right(self):
        after = polish.annotate(self.before)
        polish.validate(after)
        self.assertEqual(sum(bool(a["notes"][0]["body"]) for a in after["actions"]), 15)
        self.assertEqual(sum(e["type"] == "Section" for e in after["gui"]["elements"]), 5)
        self.assertEqual(polish.logic(after), polish.logic(self.before))

    def test_annotation_is_idempotent(self):
        first = polish.annotate(self.before)
        self.assertEqual(polish.annotate(first), first)

    def test_unknown_tile_fails_instead_of_publishing_partial_layout(self):
        self.before["actions"][0]["name"] = "unexpected input"
        with self.assertRaises(ValueError):
            polish.annotate(self.before)

    def test_coordinate_copy_corruption_is_detected(self):
        after = polish.annotate(self.before)
        after["actions"][0]["gui"]["x"] += 10
        with self.assertRaises(AssertionError):
            polish.validate(after)

    def test_backward_edge_and_overlap_are_detected(self):
        after = polish.annotate(self.before)
        corrupt = copy.deepcopy(after)
        corrupt["gui"]["elements"][0]["x"] = corrupt["gui"]["elements"][1]["x"]
        corrupt["gui"]["elements"][0]["y"] = corrupt["gui"]["elements"][1]["y"]
        corrupt["gui"]["canvases"]["default"]["elements"] = copy.deepcopy(corrupt["gui"]["elements"])
        with self.assertRaises(AssertionError):
            polish.validate(corrupt)


if __name__ == "__main__":
    unittest.main()
