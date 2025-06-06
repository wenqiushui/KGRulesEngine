# examples/elevator_panel_simplified/scripts/determine_stiffeners.py
import sys
import json
from typing import Dict, Any, List

# Define expected namespaces
EX_NS = "http://kce.com/example/elevator_panel#"

def calculate_stiffener_count_for_panel(panel_width: int) -> int:
    """
    Calculates the number of stiffeners for a panel based on its width.
    Rules:
    - Width > 500: 2 stiffeners
    - Width > 300 and <= 500: 1 stiffener
    - Width <= 300: 0 stiffeners
    """
    if panel_width > 500:
        return 2
    elif panel_width > 300: # Implies panel_width <= 500 due to previous condition
        return 1
    else: # panel_width <= 300
        return 0

def process_all_panels_stiffeners(
    panels_info_json_str: str # JSON string: [{"uri": "uri1", "width": width1}, ...]
) -> Dict[str, Any]:
    """
    Processes all panels to determine their stiffener counts.
    """
    try:
        panels_info_list = json.loads(panels_info_json_str)
        if not isinstance(panels_info_list, list):
            raise ValueError("Panels info is not a list.")
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON string for panels_info_list.")

    rdf_updates_for_panels = []

    for panel_data in panels_info_list:
        if not isinstance(panel_data, dict) or "uri" not in panel_data or "width" not in panel_data:
            print(f"Warning: Skipping invalid panel data entry for stiffeners: {panel_data}", file=sys.stderr)
            continue
        
        panel_uri = panel_data["uri"]
        panel_width = panel_data["width"]

        if not isinstance(panel_width, int):
            print(f"Warning: Panel width for {panel_uri} is not an integer. Skipping stiffener calculation.", file=sys.stderr)
            continue
            
        stiffener_count = calculate_stiffener_count_for_panel(panel_width)
        
        properties_to_set = {
            EX_NS + "stiffenerCount": stiffener_count
        }
        
        rdf_updates_for_panels.append({
            "uri": panel_uri,
            "properties_to_set": properties_to_set
        })

    return {
        "stiffeners_determined_flag_output": True, # Output parameter name from nodes.yaml
        "_rdf_instructions": {
            "update_entities": rdf_updates_for_panels
        }
    }

if __name__ == "__main__":
    # Expected command line arguments:
    # 1: panels_info_json_str (JSON string of list of panel dicts [{'uri': '...', 'width': ...}])
    # 2: rear_wall_assembly_uri (string, for context, though not directly used by core logic here)
    if len(sys.argv) != 3:
        print(f"Usage: python {sys.argv[0]} <panels_info_json_string> <rear_wall_assembly_uri>", file=sys.stderr)
        sys.exit(1)

    try:
        arg_panels_info_json_str = sys.argv[1]
        arg_rear_wall_assembly_uri = sys.argv[2] # Received for context

        result_data = process_all_panels_stiffeners(
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
