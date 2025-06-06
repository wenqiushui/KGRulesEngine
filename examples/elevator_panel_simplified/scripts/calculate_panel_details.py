# examples/elevator_panel_simplified/scripts/calculate_panel_details.py
import sys
import json
from typing import Dict, Any, List

# Define expected namespaces (matching those in utils.py and ontologies)
EX_NS = "http://kce.com/example/elevator_panel#"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"

# Default values (could also be passed as parameters if they vary)
CENTER_PANEL_WIDTH = 700

def calculate_dimensions_for_panel(
    panel_data: Dict[str, Any], # Contains 'uri' and 'name' of the panel
    car_internal_width: int,
    car_internal_height: int,
    number_of_panels: int # Assuming 3 for now, could be derived or passed
) -> Dict[str, Any]:
    """Calculates thickness, bending height, and width for a single panel."""
    panel_name = panel_data.get("name", "")
    
    # 1. Calculate thickness and bending height based on carInternalHeight
    if car_internal_height > 2300:
        thickness = 1.5
        bending_height = 34
    else:
        thickness = 1.3
        bending_height = 25

    # 2. Calculate panel width
    # Assuming a 3-panel configuration: Left, Center, Right
    # And panel_name helps identify (e.g., contains "Center")
    actual_panel_width = 0
    if number_of_panels == 3: # Simplified logic for 3 panels
        if "CenterRearPanel" in panel_name: # Check if this naming convention is reliable
            actual_panel_width = CENTER_PANEL_WIDTH
        else: # Left or Right panel
            actual_panel_width = (car_internal_width - CENTER_PANEL_WIDTH) / 2
            if not actual_panel_width.is_integer():
                 # Handle cases where division is not clean, though typically it should be
                 # Forcing int for now, real design might need float or error
                print(f"Warning: Side panel width for {panel_name} is not an integer ({actual_panel_width}). Rounding down.", file=sys.stderr)
                actual_panel_width = int(actual_panel_width)
            else:
                actual_panel_width = int(actual_panel_width)

    elif number_of_panels == 1: # If only one panel (e.g. very narrow car, or different logic)
        actual_panel_width = car_internal_width
    # Add logic for 4 panels if car_internal_width > 2100 as per later rules
    # For MVP, stick to 3 panels as primary logic from problem description
    else:
        # Default or error for other panel counts if not handled
        print(f"Warning: Panel width calculation not defined for {number_of_panels} panels. Defaulting width for {panel_name}.", file=sys.stderr)
        actual_panel_width = car_internal_width / number_of_panels # Simplistic fallback


    return {
        EX_NS + "panelThickness": thickness,
        EX_NS + "bendingHeight": bending_height,
        EX_NS + "panelWidth": actual_panel_width
        # panelHeight is assumed to be already set to car_internal_height by init_rear_wall.py
    }

def process_all_panels_details(
    car_internal_width: int,
    car_internal_height: int,
    panels_info_json_str: str # JSON string: [{"uri": "uri1", "name": "name1"}, ...]
) -> Dict[str, Any]:
    """
    Processes all panels to calculate their details.

    Returns:
        A dictionary structured for NodeExecutor to update RDF.
        The key "panels_details_calculated_flag_output" matches the 'name' of the output parameter
        in nodes.yaml for ex:CalculatePanelDetailsNode.
        The "_rdf_updates" key contains specific instructions.
    """
    try:
        panels_info_list = json.loads(panels_info_json_str)
        if not isinstance(panels_info_list, list):
            raise ValueError("Panels info is not a list.")
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON string for panels_info_list.")

    rdf_updates_for_panels = []
    num_panels = len(panels_info_list) # Get number of panels from the input list

    for panel_data in panels_info_list:
        if not isinstance(panel_data, dict) or "uri" not in panel_data or "name" not in panel_data:
            print(f"Warning: Skipping invalid panel data entry: {panel_data}", file=sys.stderr)
            continue
        
        calculated_properties = calculate_dimensions_for_panel(
            panel_data,
            car_internal_width,
            car_internal_height,
            num_panels
        )
        rdf_updates_for_panels.append({
            "uri": panel_data["uri"],
            "properties_to_set": calculated_properties
        })

    return {
        "panels_details_calculated_flag_output": True, # Output parameter name from nodes.yaml
        "_rdf_instructions": {
            "update_entities": rdf_updates_for_panels # NodeExecutor needs to handle this
        }
    }


if __name__ == "__main__":
    # Expected command line arguments:
    # 1: car_internal_width (int)
    # 2: car_internal_height (int)
    # 3: panels_info_json_str (JSON string of list of panel dicts [{'uri': '...', 'name': '...'}])
    # 4: rear_wall_assembly_uri (string, used for context if needed, but logic here uses panel list)
    # The 'rear_wall_assembly_uri' defined as input in nodes.yaml will be passed,
    # but this script's logic now primarily uses the 'panels_info_json_str'.
    # It's good practice for the script to expect all defined inputs even if not all are used in its core logic.

    if len(sys.argv) != 5: # car_width, car_height, panels_json, assembly_uri
        print(f"Usage: python {sys.argv[0]} <car_internal_width> <car_internal_height> <panels_info_json_string> <rear_wall_assembly_uri>", file=sys.stderr)
        sys.exit(1)

    try:
        arg_car_internal_width = int(sys.argv[1])
        arg_car_internal_height = int(sys.argv[2])
        arg_panels_info_json_str = sys.argv[3]
        arg_rear_wall_assembly_uri = sys.argv[4] # Received but not directly used in this script's core logic

        result_data = process_all_panels_details(
            arg_car_internal_width,
            arg_car_internal_height,
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
