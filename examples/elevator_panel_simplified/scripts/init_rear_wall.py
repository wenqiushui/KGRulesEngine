# examples/elevator_panel_simplified/scripts/init_rear_wall.py
import sys
import json
import uuid
from typing import Dict, Any, List

# Define expected namespaces (matching those in utils.py and ontologies)
EX_NS = "http://kce.com/example/elevator_panel#"
KCE_NS = "http://kce.com/ontology/core#" # Not strictly needed by this script's logic directly
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type" # rdf:type URI


def generate_uri(namespace: str, local_name_base: str, unique_suffix: str) -> str:
    """Generates a URI string."""
    return f"{namespace}{local_name_base}_{unique_suffix}"

def create_rear_wall_initial_data(car_internal_width: int, car_internal_height: int, workflow_instance_uri_str: str) -> Dict[str, Any]:
    """
    Generates the data structure for initializing a rear wall assembly and its panels.
    This data structure will be interpreted by NodeExecutor to create RDF.
    """
    run_specific_suffix = workflow_instance_uri_str.split('/')[-1] if '/' in workflow_instance_uri_str else str(uuid.uuid4()).split('-')[0]

    # 1. RearWallAssembly instance data
    rear_wall_assembly_uri = generate_uri(EX_NS, "RearWallAssembly", run_specific_suffix)
    assembly_initial_props = {
        EX_NS + "carInternalWidth": car_internal_width,
        EX_NS + "carInternalHeight": car_internal_height,
        EX_NS + "assemblyTotalWidth": car_internal_width,
        EX_NS + "assemblyTotalHeight": car_internal_height
    }

    # 2. ElevatorPanel instances data (Left, Center, Right for 3-panel setup)
    panel_base_names = ["LeftRearPanel", "CenterRearPanel", "RightRearPanel"]
    panel_creations_data = []

    for name_base in panel_base_names:
        panel_uri = generate_uri(EX_NS, name_base, run_specific_suffix)
        panel_initial_props = {
            EX_NS + "panelName": f"{name_base}_{run_specific_suffix}",
            EX_NS + "panelHeight": car_internal_height # Initial height
        }
        panel_creations_data.append({
            "uri": panel_uri,
            "type": EX_NS + "ElevatorPanel",
            "properties": panel_initial_props,
            "link_to_parent": {
                "parent_uri": rear_wall_assembly_uri,
                "link_property": EX_NS + "hasPanelPart"
            }
        })

    # This is the structured output NodeExecutor will need to parse
    # to perform actual RDF modifications.
    # The key "rear_wall_assembly_uri_output" matches the 'name' of the output parameter
    # defined in nodes.yaml for ex:InitializeRearWallNode. Its value will be stored
    # on the workflow_instance_context_uri by the NodeExecutor.
    # The "_rdf_instructions" key is a convention for this script to pass detailed
    # RDF modification instructions to an enhanced NodeExecutor.
    return {
        "rear_wall_assembly_uri_output": rear_wall_assembly_uri, # Main output to be mapped
        "_rdf_instructions": {
            "create_entities": [
                {
                    "uri": rear_wall_assembly_uri,
                    "type": EX_NS + "RearWallAssembly",
                    "properties": assembly_initial_props
                }
            ] + [
                {
                    "uri": p_data["uri"],
                    "type": p_data["type"],
                    "properties": p_data["properties"]
                } for p_data in panel_creations_data
            ],
            "add_links": [
                {
                    "subject": p_data["link_to_parent"]["parent_uri"],
                    "predicate": p_data["link_to_parent"]["link_property"],
                    "object": p_data["uri"]
                } for p_data in panel_creations_data
            ]
        }
    }

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(f"Usage: python {sys.argv[0]} <car_internal_width> <car_internal_height> <workflow_instance_uri>", file=sys.stderr)
        sys.exit(1)

    try:
        arg_car_internal_width = int(sys.argv[1])
        arg_car_internal_height = int(sys.argv[2])
        arg_workflow_instance_uri_str = sys.argv[3]

        result_data = create_rear_wall_initial_data(
            arg_car_internal_width,
            arg_car_internal_height,
            arg_workflow_instance_uri_str
        )
        print(json.dumps(result_data))
        sys.exit(0)

    except ValueError as e:
        print(f"Error: Invalid input value - {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred in {sys.argv[0]}: {e}", file=sys.stderr)
        sys.exit(1)
