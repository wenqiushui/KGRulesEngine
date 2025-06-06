# examples/elevator_panel_simplified/scripts/sum_assembly_costs.py
import sys
import json
from typing import Dict, Any, List

# Define expected namespaces
EX_NS = "http://kce.com/example/elevator_panel#"

def calculate_total_assembly_cost(
    assembly_uri: str,
    panels_cost_info_json_str: str # JSON string: [{"uri": "uri1", "panelTotalCost": cost1}, ...]
) -> Dict[str, Any]:
    """
    Calculates the total cost of the assembly by summing the total costs of its panels.
    """
    try:
        panels_cost_info_list = json.loads(panels_cost_info_json_str)
        if not isinstance(panels_cost_info_list, list):
            raise ValueError("Panels cost info is not a list.")
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON string for panels_cost_info_list.")

    total_assembly_cost = 0.0

    for panel_data in panels_cost_info_list:
        if not isinstance(panel_data, dict) or "panelTotalCost" not in panel_data:
            # URI might not be strictly needed for sum, but good for validation if present
            panel_uri_for_log = panel_data.get("uri", "UnknownPanel")
            print(f"Warning: Skipping panel data due to missing 'panelTotalCost': {panel_data.get('uri', panel_uri_for_log)}", file=sys.stderr)
            continue
        
        try:
            panel_cost = float(panel_data["panelTotalCost"])
            total_assembly_cost += panel_cost
        except (TypeError, ValueError) :
            panel_uri_for_log = panel_data.get("uri", "UnknownPanel")
            print(f"Warning: Invalid panelTotalCost value for panel {panel_uri_for_log}. Skipping.", file=sys.stderr)
            continue
            
    properties_to_set_on_assembly = {
        EX_NS + "assemblyTotalCost": round(total_assembly_cost, 2)
    }
    
    rdf_updates_for_assembly = [{
        "uri": assembly_uri,
        "properties_to_set": properties_to_set_on_assembly
    }]

    return {
        "assembly_cost_calculated_flag_output": True, # Output parameter name from nodes.yaml
        "_rdf_instructions": {
            "update_entities": rdf_updates_for_assembly
        }
    }

if __name__ == "__main__":
    # Expected command line arguments:
    # 1: rear_wall_assembly_uri (string)
    # 2: panels_cost_info_json_str (JSON string of list of panel dicts [{'uri': '...', 'panelTotalCost': ...}])
    if len(sys.argv) != 3:
        print(f"Usage: python {sys.argv[0]} <rear_wall_assembly_uri> <panels_cost_info_json_string>", file=sys.stderr)
        sys.exit(1)

    try:
        arg_rear_wall_assembly_uri = sys.argv[1]
        arg_panels_cost_info_json_str = sys.argv[2]

        result_data = calculate_total_assembly_cost(
            arg_rear_wall_assembly_uri,
            arg_panels_cost_info_json_str
        )
        print(json.dumps(result_data))
        sys.exit(0)

    except ValueError as e:
        print(f"Error: Invalid input value - {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred in {sys.argv[0]}: {e}", file=sys.stderr)
        sys.exit(1)
