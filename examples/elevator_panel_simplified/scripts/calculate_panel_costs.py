# examples/elevator_panel_simplified/scripts/calculate_panel_costs.py
import sys
import json
from typing import Dict, Any, List

# Define expected namespaces
EX_NS = "http://kce.com/example/elevator_panel#"

# Costing rules from the problem description
BENDING_COST_PER_PANEL = 30.0
COST_PER_HOLE = 0.5

MATERIAL_COST_RULES = {
    1.3: { # Thickness
        "lte_500": 400.0, # Width <= 500
        "gt_500": 600.0   # Width > 500
    },
    1.5: {
        "lte_500": 500.0,
        "gt_500": 800.0
    }
}

def calculate_costs_for_panel(
    panel_thickness: float,
    panel_width: int,
    bolt_hole_count: int,
    # stiffener_count is not directly used in cost calculation rules provided,
    # but it's good to receive it if it might influence other indirect costs later.
    stiffener_count: int # pylint: disable=unused-argument 
) -> Dict[str, float]:
    """
    Calculates material, processing, and total costs for a single panel.
    """
    # 1. Material Cost
    material_cost = 0.0
    thickness_rules = MATERIAL_COST_RULES.get(panel_thickness)
    if thickness_rules:
        if panel_width <= 500:
            material_cost = thickness_rules.get("lte_500", 0.0)
        else:
            material_cost = thickness_rules.get("gt_500", 0.0)
    else:
        print(f"Warning: No material cost rule found for thickness {panel_thickness}. Material cost set to 0.", file=sys.stderr)

    # 2. Processing Cost (Bending + Holes)
    # Assuming every panel has bending cost.
    processing_cost_bending = BENDING_COST_PER_PANEL
    processing_cost_holes = bolt_hole_count * COST_PER_HOLE
    processing_cost = processing_cost_bending + processing_cost_holes
    
    # 3. Total Panel Cost
    total_panel_cost = material_cost + processing_cost

    return {
        EX_NS + "materialCost": round(material_cost, 2),
        EX_NS + "processingCost": round(processing_cost, 2),
        EX_NS + "panelTotalCost": round(total_panel_cost, 2)
    }

def process_all_panels_costs(
    panels_info_json_str: str # JSON string: [{"uri": "uri1", "thickness": t1, "width": w1, "boltHoleCount": bh1, "stiffenerCount": sc1}, ...]
) -> Dict[str, Any]:
    """
    Processes all panels to calculate their costs.
    """
    try:
        panels_info_list = json.loads(panels_info_json_str)
        if not isinstance(panels_info_list, list):
            raise ValueError("Panels info is not a list.")
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON string for panels_info_list.")

    rdf_updates_for_panels = []

    for panel_data in panels_info_list:
        required_keys = ["uri", "thickness", "width", "boltHoleCount", "stiffenerCount"]
        if not (isinstance(panel_data, dict) and all(key in panel_data for key in required_keys)):
            print(f"Warning: Skipping invalid panel data entry for costs: {panel_data}", file=sys.stderr)
            continue
        
        panel_uri = panel_data["uri"]
        try:
            panel_thickness = float(panel_data["thickness"])
            panel_width = int(panel_data["width"])
            bolt_hole_count = int(panel_data["boltHoleCount"])
            stiffener_count = int(panel_data["stiffenerCount"])
        except ValueError:
            print(f"Warning: Invalid data types for panel {panel_uri}. Skipping cost calculation.", file=sys.stderr)
            continue
            
        cost_properties = calculate_costs_for_panel(
            panel_thickness,
            panel_width,
            bolt_hole_count,
            stiffener_count
        )
        
        rdf_updates_for_panels.append({
            "uri": panel_uri,
            "properties_to_set": cost_properties
        })

    return {
        "panel_costs_calculated_flag_output": True, # Output parameter name from nodes.yaml
        "_rdf_instructions": {
            "update_entities": rdf_updates_for_panels
        }
    }

if __name__ == "__main__":
    # Expected command line arguments:
    # 1: panels_info_json_str (JSON string of list of panel dicts)
    # 2: rear_wall_assembly_uri (string, for context, though not directly used by core logic here)
    if len(sys.argv) != 3:
        print(f"Usage: python {sys.argv[0]} <panels_info_json_string> <rear_wall_assembly_uri>", file=sys.stderr)
        sys.exit(1)

    try:
        arg_panels_info_json_str = sys.argv[1]
        arg_rear_wall_assembly_uri = sys.argv[2] # Received for context

        result_data = process_all_panels_costs(
            arg_panels_info_json_str
        )
        print(json.dumps(result_data))
        sys.exit(0)

    except ValueError as e:
        print(f"Error: Invalid input value - {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred in {sys.argv[0]}: {e}", file=sys.stderr)
        sys.exit(1)
