import unittest
import json
import math # For ceil calculation
from graph_pattern_engine import GraphPatternEngine

# Expected outputs - defined globally for clarity or within the class as class attributes

# Initial Design Expected Outputs
EXPECTED_INITIAL_JOINTS = {
  "joints": [
    {
      "name": "左后壁-中间后壁-平齐", "type": "平齐", "part1_n": "左后壁",
      "select_m1": "parall-xz-nearest-face", "part2_n": "中间后壁", "select_m2": "parall-xz-nearest-face"
    },
    {
      "name": "左后壁-右后壁-平齐", "type": "平齐", "part1_n": "左后壁",
      "select_m1": "parall-xz-nearest-face", "part2_n": "右后壁", "select_m2": "parall-xz-nearest-face"
    },
    {
      "name": "左后壁-中间后壁-平齐001", "type": "平齐", "part1_n": "左后壁",
      "select_m1": "parall-xy-nearest-face", "part2_n": "中间后壁", "select_m2": "parall-xy-nearest-face"
    },
    {
      "name": "左后壁-右后壁-平齐001", "type": "平齐", "part1_n": "左后壁",
      "select_m1": "parall-xy-nearest-face", "part2_n": "右后壁", "select_m2": "parall-xy-nearest-face"
    },
    {
      "name": "左后壁-中间后壁-接触", "type": "接触", "part1_n": "左后壁",
      "select_m1": "parall-yz-farthest-face", "part2_n": "中间后壁", "select_m2": "parall-yz-nearest-face"
    },
    {
      "name": "中间后壁-右后壁-接触", "type": "接触", "part1_n": "中间后壁",
      "select_m1": "parall-yz-farthest-face", "part2_n": "右后壁", "select_m2": "parall-yz-nearest-face"
    }
  ]
}

# Height 2450, Width 1500. Holes = ceil(2450/300)*2 = 9*2 = 18
EXPECTED_INITIAL_DIMENSIONS = {
  "轿厢后壁板尺寸": [
    {"壁板名称":"左后壁","壁板厚度":1.5,"折弯高度":34,"宽度":400.0,"高度":2450.0,"螺孔数量":18,"加强筋数量":1},
    {"壁板名称":"中间后壁","壁板厚度":1.5,"折弯高度":34,"宽度":700.0,"高度":2450.0,"螺孔数量":18,"加强筋数量":2},
    {"壁板名称":"右后壁","壁板厚度":1.5,"折弯高度":34,"宽度":400.0,"高度":2450.0,"螺孔数量":18,"加强筋数量":1}
  ]
}

EXPECTED_INITIAL_COSTS = [
  {"壁板名称":"左后壁", "材料成本":500.0, "加工成本":39.0, "总成本":539.0},
  {"壁板名称":"中间后壁", "材料成本":800.0, "加工成本":39.0, "总成本":839.0},
  {"壁板名称":"右后壁", "材料成本":500.0, "加工成本":39.0, "总成本":539.0}
]

# Changed Design Expected Outputs
# Height 2450, Width 2200. Holes = ceil(2450/300)*2 = 9*2 = 18
EXPECTED_CHANGED_DIMENSIONS = {
  "轿厢后壁板尺寸": [
    {"壁板名称":"左后壁","壁板厚度":1.5,"折弯高度":34,"宽度":400.0,"高度":2450.0,"螺孔数量":18,"加强筋数量":1},
    {"壁板名称":"中间后壁","壁板厚度":1.5,"折弯高度":34,"宽度":700.0,"高度":2450.0,"螺孔数量":18,"加强筋数量":2},
    {"壁板名称":"中间后壁001","壁板厚度":1.5,"折弯高度":34,"宽度":700.0,"高度":2450.0,"螺孔数量":18,"加强筋数量":2},
    {"壁板名称":"右后壁","壁板厚度":1.5,"折弯高度":34,"宽度":400.0,"高度":2450.0,"螺孔数量":18,"加强筋数量":1}
  ]
}

EXPECTED_CHANGED_JOINTS = {
  "joints": [
    {"name": "左后壁-中间后壁-平齐", "type": "平齐", "part1_n": "左后壁", "select_m1": "parall-xz-nearest-face", "part2_n": "中间后壁", "select_m2": "parall-xz-nearest-face"},
    {"name": "中间后壁-中间后壁001-平齐", "type": "平齐", "part1_n": "中间后壁", "select_m1": "parall-xz-nearest-face", "part2_n": "中间后壁001", "select_m2": "parall-xz-nearest-face"},
    {"name": "中间后壁001-右后壁-平齐", "type": "平齐", "part1_n": "中间后壁001", "select_m1": "parall-xz-nearest-face", "part2_n": "右后壁", "select_m2": "parall-xz-nearest-face"},
    {"name": "左后壁-中间后壁-平齐001", "type": "平齐", "part1_n": "左后壁", "select_m1": "parall-xy-nearest-face", "part2_n": "中间后壁", "select_m2": "parall-xy-nearest-face"},
    {"name": "中间后壁-中间后壁001-平齐001", "type": "平齐", "part1_n": "中间后壁", "select_m1": "parall-xy-nearest-face", "part2_n": "中间后壁001", "select_m2": "parall-xy-nearest-face"},
    {"name": "中间后壁001-右后壁-平齐001", "type": "平齐", "part1_n": "中间后壁001", "select_m1": "parall-xy-nearest-face", "part2_n": "右后壁", "select_m2": "parall-xy-nearest-face"},
    {"name": "左后壁-中间后壁-接触", "type": "接触", "part1_n": "左后壁", "select_m1": "parall-yz-farthest-face", "part2_n": "中间后壁", "select_m2": "parall-yz-nearest-face"},
    {"name": "中间后壁-中间后壁001-接触", "type": "接触", "part1_n": "中间后壁", "select_m1": "parall-yz-farthest-face", "part2_n": "中间后壁001", "select_m2": "parall-yz-nearest-face"},
    {"name": "中间后壁001-右后壁-接触", "type": "接触", "part1_n": "中间后壁001", "select_m1": "parall-yz-farthest-face", "part2_n": "右后壁", "select_m2": "parall-yz-nearest-face"}
  ]
}

EXPECTED_CHANGED_COSTS = [
  {"壁板名称":"左后壁", "材料成本":500.0, "加工成本":39.0, "总成本":539.0},
  {"壁板名称":"中间后壁", "材料成本":800.0, "加工成本":39.0, "总成本":839.0},
  {"壁板名称":"中间后壁001", "材料成本":800.0, "加工成本":39.0, "总成本":839.0},
  {"壁板名称":"右后壁", "材料成本":500.0, "加工成本":39.0, "总成本":539.0}
]


class TestWallPanelScenarios(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = GraphPatternEngine()
        cls.engine.load_ontology("ontology.ttl")
        cls.engine.load_rules("rules.ttl")
        cls.engine.load_templates("templates.ttl")

    def _parse_actual_joints(self, result_str):
        # Handles potential single quotes from engine and ensures "joints" key exists
        # The engine output for joints is expected to be a string that is a valid JSON object itself
        # once quotes are corrected.
        return json.loads(result_str.replace("'", '"'))

    def _parse_actual_dimensions_or_costs(self, result_str_list_content):
        # Handles potential single quotes and wraps with [] if engine returns comma separated objects
        # e.g. "obj1, obj2" -> "[obj1, obj2]"
        # It seems the engine returns something like:
        # '{"壁板名称":"左后壁",...}', '{"壁板名称":"中间后壁",...}'
        # which needs to be made into a valid JSON array string.
        processed_str = f"[{result_str_list_content}]".replace("'", '"')
        return json.loads(processed_str)

    def test_initial_design_scenario(self):
        # Test 1: Initial Design - Joint Generation
        context_initial = {}
        result_joints_initial = self.engine.query("http://example.com/ontology#JointGeneration", context_initial)
        actual_joints_initial = self._parse_actual_joints(result_joints_initial["_:result"]["joints"])
        # For comparing lists of dicts where order might not be guaranteed by the engine for all items,
        # but is fixed in our expected output, sort both by a unique key, e.g. 'name'.
        # However, the problem states "order of items in JSON arrays (lists) matters". So, direct comparison.
        self.assertEqual(actual_joints_initial, EXPECTED_INITIAL_JOINTS)

        # Test 2: Initial Design - Dimension Calculation
        context_initial_dims = {
            "cabinet_height": 2450,
            "cabinet_width": 1500
        }
        result_dims_initial = self.engine.query("http://example.com/ontology#DimensionCalculation", context_initial_dims)
        actual_dims_initial_list = self._parse_actual_dimensions_or_costs(result_dims_initial["_:result"]["dimensions"])
        actual_dims_initial = {"轿厢后壁板尺寸": actual_dims_initial_list}
        self.assertEqual(actual_dims_initial, EXPECTED_INITIAL_DIMENSIONS)

        # Test 3: Initial Design - Cost Calculation
        # Context from dimension calculation is reused
        result_costs_initial = self.engine.query("http://example.com/ontology#CostCalculation", context_initial_dims)
        actual_costs_initial = self._parse_actual_dimensions_or_costs(result_costs_initial["_:result"]["costs"])
        self.assertEqual(actual_costs_initial, EXPECTED_INITIAL_COSTS)

    def test_changed_design_scenario(self):
        # Test 4: Design Change Trigger
        context_changed = {
            "cabinet_height": 2450,
            "cabinet_width": 2200  # Width change triggers different rules
        }
        # This query is for triggering the change, its direct output might not be tested here,
        # but it affects subsequent queries.
        self.engine.query("http://example.com/ontology#DesignChange", context_changed)

        # Test 5: Changed Design - Dimension Calculation
        result_dims_changed = self.engine.query("http://example.com/ontology#DimensionCalculation", context_changed)
        actual_dims_changed_list = self._parse_actual_dimensions_or_costs(result_dims_changed["_:result"]["dimensions"])
        actual_dims_changed = {"轿厢后壁板尺寸": actual_dims_changed_list}
        self.assertEqual(actual_dims_changed, EXPECTED_CHANGED_DIMENSIONS)

        # Test 6: Changed Design - Joint Generation
        result_joints_changed = self.engine.query("http://example.com/ontology#JointGeneration", context_changed)
        actual_joints_changed = self._parse_actual_joints(result_joints_changed["_:result"]["joints"])
        # Assuming order matters as per problem description for changed joints as well.
        self.assertEqual(actual_joints_changed, EXPECTED_CHANGED_JOINTS)
        
        # Test 7: Changed Design - Cost Calculation
        result_costs_changed = self.engine.query("http://example.com/ontology#CostCalculation", context_changed)
        actual_costs_changed = self._parse_actual_dimensions_or_costs(result_costs_changed["_:result"]["costs"])
        self.assertEqual(actual_costs_changed, EXPECTED_CHANGED_COSTS)

if __name__ == "__main__":
    unittest.main()
