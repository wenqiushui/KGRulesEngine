# KCE User Guide: Getting Started

**Version:** 0.1.0 (MVP)

Welcome to the Knowledge-CAD-Engine (KCE)! This guide will walk you through setting up KCE, understanding its basic concepts, and running your first simple workflow.

## 1. Introduction

Knowledge-CAD-Engine (KCE) is a framework designed to automate design and calculation processes by combining:
*   **Knowledge Representation:** Using RDF and OWL to define domain knowledge and component metadata.
*   **Node-Based Workflows:** Defining processes as sequences of executable nodes (atomic or composite).
*   **External Script Integration:** Allowing atomic nodes to execute external Python scripts.
*   **Declarative Rules:** Using simple rules to influence workflow execution.
*   **Provenance Tracking:** Recording execution history and data lineage.

This MVP (Minimum Viable Product) provides core functionalities to demonstrate these concepts.

## 2. Prerequisites

*   **Python:** Version 3.8 or higher.
*   **Pip:** Python package installer.
*   **Git:** For cloning the KCE repository (if applicable).

## 3. Installation

Currently, KCE is run directly from its source code or can be installed as a Python package if `setup.py` is provided and configured.

**Option 1: Running from Source (Recommended for MVP Development/Testing)**

1.  **Clone the Repository (if you have one):**
    ```bash
    git clone <your_kce_repository_url>
    cd knowledge-cad-engine
    ```
    If you don't have a repository, ensure you have the KCE source code directory.

2.  **Create a Virtual Environment (Recommended):**
    ```bash
    python -m venv .venv
    # Activate it:
    # On Windows:
    # .venv\Scripts\activate
    # On macOS/Linux:
    # source .venv/bin/activate
    ```

3.  **Install Dependencies:**
    Navigate to the project root directory (where `requirements.txt` is located) and run:
    ```bash
    pip install -r requirements.txt
    ```
    This will install `rdflib`, `owlrl`, `rdflib-sqlite`, `pyyaml`, `click`, etc.

**Option 2: Installing as a Package (If `setup.py` is configured)**

If a `setup.py` file is configured with an entry point for the CLI:
```bash
pip install .
# This might make a `kce-cli` command available globally or in your virtual environment.
```
For this guide, we'll assume you are running from source and the CLI is invoked via `python -m cli.main`.

## 4. Core Concepts

Before running KCE, it's helpful to understand its main components:

*   **Ontologies:**
    *   **`kce_core_ontology_v0.2.ttl`**: Defines the KCE framework's vocabulary (Nodes, Workflows, Rules, Parameters, etc.). This is a general-purpose ontology.
    *   **(Domain Ontology - e.g., `elevator_panel_ontology.ttl`)**: Defines concepts specific to your problem domain (e.g., `ex:ElevatorPanel`, `ex:panelWidth`). You'll create or use this.
*   **Definitions (YAML files):**
    *   **Nodes (`nodes.yaml`):** Describe executable units.
        *   `AtomicNode`: Executes an external Python script. Specifies inputs, outputs, and the script path.
        *   `CompositeNode`: Represents a sub-workflow, referencing another workflow definition.
    *   **Rules (`rules.yaml`):** Define simple `IF (SPARQL ASK condition) THEN (trigger action_node_uri)` logic.
    *   **Workflows (`workflows.yaml`):** Define a sequence of steps, where each step executes a Node.
*   **RDF Store (Knowledge Base):**
    *   An SQLite database (`kce_store.sqlite` by default) or an in-memory store.
    *   Stores all loaded ontologies, definitions (converted to RDF), instance data generated during execution, and provenance logs.
*   **Python Scripts:** External scripts executed by `AtomicNode`s. They receive inputs (e.g., via command-line arguments) and produce outputs (e.g., JSON to stdout).
*   **Workflow Instance Context:** A unique RDF resource (URI) created for each top-level workflow run. Initial parameters are attached to this context, and nodes read/write data related to this context.

## 5. Directory Structure Overview

A typical KCE project might have:
```
knowledge-cad-engine/
├── cli/
│   └── main.py           # CLI entry point
├── kce_core/             # Core KCE library
│   └── ...
├── ontologies/
│   ├── kce_core_ontology_v0.2.ttl
│   └── (your_domain_ontology.ttl)
├── examples/
│   └── your_first_project/
│       ├── definitions/
│       │   ├── nodes.yaml
│       │   ├── rules.yaml
│       │   └── workflows.yaml
│       ├── params/
│       │   └── scenario1_params.json
│       └── scripts/
│           └── your_script.py
├── kce_store.sqlite      # Default RDF database (created on first run with DB path)
└── requirements.txt
```

## 6. Running KCE: Step-by-Step Tutorial

Let's walk through a simplified "Elevator Panel Configuration" example. Assume you have an example project under `examples/elevator_panel_simplified/` with the necessary YAML definition files and Python scripts.

**Step 1: Prepare your KCE environment (CLI)**

Ensure your virtual environment is activated and you are in the root `knowledge-cad-engine` directory.
The KCE CLI is invoked using `python -m cli.main`. For brevity, we'll refer to this as `kce-cli`.

**Example:**
```bash
python -m cli.main --help
```
This should display the available commands.

**Step 2: Initialize the Database and Load Core Ontology**

The first time you use KCE with a persistent database, or if you want to start fresh, initialize it:

```bash
kce-cli init-db
```
This command:
*   Prompts for confirmation to clear the database (default: `kce_store.sqlite`).
*   Clears/creates the database.
*   Loads the `kce_core_ontology_v0.2.ttl` by default.

You can specify a different database path:
```bash
kce-cli --db-path my_project.sqlite init-db
```
Or use an in-memory store for a temporary session:
```bash
kce-cli --in-memory init-db
```

**Step 3: Load Domain-Specific Ontology (If any)**

If your project uses a specific domain ontology (e.g., defining `ex:ElevatorPanel`), load it using the `query` command with a `LOAD` statement (SPARQL Update), or by parsing it if you add a dedicated CLI command for it. For MVP, you might manually ensure it's loaded or combine it with core ontology if simple. A more robust way is to ensure your `DefinitionLoader` or `StoreManager` can load multiple ontology files at startup or via a command.

If your domain ontology is `elevator_panel_ontology.ttl`:
```bash
# Assuming your StoreManager or init-db can load multiple ontologies,
# or you use a SPARQL LOAD command (more advanced).
# For MVP, let's assume it's handled during init or by loading definitions
# that reference its terms.
# If you need to load it separately after init-db:
kce-cli query "LOAD <file:///path/to/your/ontologies/elevator_panel_ontology.ttl>"
# Note: File URIs need to be absolute and correctly formatted.
```
*(This step might be simplified in MVP if the domain ontology is small and included with `load-defs` indirectly, or if `init-db` is enhanced to load user ontologies.)*

**Step 4: Load Project Definitions (Nodes, Rules, Workflows)**

Your project's specific logic is defined in YAML files. Use the `load-defs` command:

```bash
kce-cli load-defs examples/elevator_panel_simplified/definitions/
```
This command will:
*   Scan the specified directory (or a single YAML file) for `.yaml` or `.yml` files.
*   Parse `nodes`, `rules`, and `workflows` sections from these files.
*   Convert these definitions into RDF triples using the KCE core ontology.
*   Store these triples in the RDF database.
*   Resolve relative `script_path` in node definitions. By default, paths are relative to the YAML file they are defined in. You can use `--base-script-path <path_to_project_root>` if all scripts are relative to a common root.
*   Perform OWL RL reasoning by default (disable with `--no-reasoning`).

**Example `nodes.yaml` snippet:**
```yaml
nodes:
  - id: "ex:CalculateThicknessNode"
    type: "AtomicNode"
    label: "Calculate Panel Thickness"
    inputs:
      - name: "panelHeight"
        maps_to_rdf_property: "ex:panelHeight"
        data_type: "integer"
    outputs:
      - name: "panelThickness"
        maps_to_rdf_property: "ex:panelThickness"
        data_type: "float"
    invocation:
      type: "PythonScript"
      script_path: "../scripts/calculate_thickness.py" # Path relative to this YAML's dir
```

**Step 5: Run a Workflow**

Once definitions are loaded, you can execute a workflow using its URI.

```bash
kce-cli run-workflow "ex:MainElevatorPanelWorkflow" \
    --params-file examples/elevator_panel_simplified/params/scenario1_params.json
```
Or with parameters as a JSON string:
```bash
kce-cli run-workflow "ex:MainElevatorPanelWorkflow" \
    --params-json '{"ex:panelWidth": 1500, "ex:panelHeight": 2450}'
```

This command will:
1.  Identify the `ex:MainElevatorPanelWorkflow` in the RDF store.
2.  If parameters are provided:
    *   Create a new "workflow instance context" URI (e.g., `<kce:instance_data/run-uuid>`).
    *   Add an `rdf:type kce:WorkflowInstanceData` triple for this context.
    *   Add the provided parameters as RDF properties of this context URI (e.g., `<context_uri> ex:panelWidth 1500 .`).
3.  Start the `WorkflowExecutor`.
4.  The executor will process workflow steps:
    *   For `AtomicNode`s, it prepares inputs by querying properties from the `current_instance_context_uri`, calls the `NodeExecutor` which runs the Python script, and then stores outputs back as properties of the `current_instance_context_uri`.
    *   For `CompositeNode`s, it recursively executes the internal workflow, managing context appropriately.
    *   After each successful node execution, it calls the `RuleEvaluator` to check if any rules should fire and potentially add new nodes to the execution queue.
5.  The `ProvenanceLogger` records the start/end of the workflow and each node, along with basic data lineage.
6.  Output will indicate success or failure.

**Step 6: Query the RDF Store (Inspect Results and Logs)**

After a workflow run, you can inspect the RDF store.

*   **View Workflow Instance Data:**
    You'll need the `run_id_uri` (logged to console or found via `show-log`) to find the `current_instance_context_uri` (e.g., `<kce:instance_data/run-uuid>`).
    ```bash
    # Assuming your context URI is <ex:InstanceDataForRunXYZ>
    kce-cli query "SELECT ?p ?o WHERE { <ex:InstanceDataForRunXYZ> ?p ?o . }"
    ```
    This will show all properties (inputs, intermediate results, final outputs) attached to your workflow instance.

*   **Show Execution Logs:**
    The `run-workflow` command should output a `Run ID URI` (e.g., `<kce:run/some-uuid>`).
    ```bash
    kce-cli show-log "kce:run/some-uuid"
    ```
    This will display:
    *   The main workflow execution log details (status, start/end times).
    *   A list of all node execution logs within that run, including their status, timings, and any error messages.

*   **Query Provenance (Basic):**
    If a node output `ex:calculatedCost` with value `500.0` was stored on `<ex:InstanceDataForRunXYZ>`, and you want to see how it was generated:
    ```bash
    # First, find the actual data resource if it's reified.
    # For MVP, if it's a literal on ex:InstanceDataForRunXYZ, provenance is linked to the node exec that modified ex:InstanceDataForRunXYZ.
    # Let's assume ex:calculatedCost points to a literal.
    # To find the node execution that last modified the context (hard to pinpoint to one property without more complex provenance):
    # More directly, if an output was reified as <ex:MyCostOutputDataEntity>:
    # kce-cli query "SELECT ?node_exec_log WHERE { <ex:MyCostOutputDataEntity> prov:wasGeneratedBy ?node_exec_log . }"
    #
    # For a simpler approach, check logs from show-log to identify node execution URIs.
    ```
    The `query-provenance` CLI command (if fully implemented in `cli/main.py` for MVP) would simplify this. For now, use `show-log` and targeted SPARQL queries.

**Step 7: Debugging**

*   **Verbose Logging:** Use the `-v` or `--verbose` global option to get DEBUG level logs from KCE components:
    ```bash
    kce-cli -v run-workflow "ex:MyWorkflow" ...
    ```
*   **Inspect RDF Store:** Use `kce-cli query` with `SELECT * WHERE { ?s ?p ?o . }` (be careful with large stores) or more specific queries to examine the state of the RDF graph.
*   **Check `stderr` of Scripts:** The `NodeExecutor` logs `stderr` from failed scripts.

## 7. Writing Your Own KCE Project

1.  **Design Your Domain Ontology:** Define the classes and properties relevant to your problem (e.g., in `my_project_ontology.ttl`).
2.  **Create Python Scripts:** Write the Python scripts that perform specific calculations or actions.
    *   **Inputs:** Decide how scripts will receive inputs (e.g., command-line arguments).
    *   **Outputs:** Scripts should output results in a way KCE can parse (MVP: JSON string to `stdout`).
3.  **Define Nodes (`nodes.yaml`):**
    *   For each script, create an `AtomicNode` definition, mapping its inputs/outputs to RDF properties from your domain ontology.
    *   Specify the `script_path` (relative to the YAML file or `--base-script-path`).
4.  **Define Rules (`rules.yaml`) (Optional):**
    *   If needed, define rules with SPARQL ASK conditions and `action_node_uri`.
5.  **Define Workflows (`workflows.yaml`):**
    *   Sequence your nodes (atomic or composite) to define the overall process.
6.  **Create Parameter Files (`params/*.json`):** For different scenarios or inputs to your workflows.
7.  **Follow Steps 2-6 above** to initialize, load, run, and inspect your KCE project.

## 8. Next Steps

This Getting Started guide covers the MVP functionalities. As KCE evolves, expect:
*   More advanced rule capabilities.
*   Complex workflow control structures (loops, parallelism).
*   Richer provenance and query capabilities.
*   GUI tools.

Explore the `examples/` directory for more detailed configurations. Check the KCE documentation (if available) or source code for more insights.
```

**Key improvements and considerations in this guide:**

*   **Clear Structure:** Organized into logical sections for easy reading.
*   **Prerequisites & Installation:** Covers the basics.
*   **Core Concepts:** Briefly explains the main ideas before diving into commands.
*   **Step-by-Step Tutorial:** Provides a narrative flow for a new user.
*   **CLI Command Examples:** Shows how to use each key CLI command defined for MVP.
*   **YAML Snippets:** Includes small examples of what definition files might look like.
*   **Explanation of What Happens:** Briefly describes the internal actions KCE takes for each command.
*   **Context URI Handling:** Emphasizes the role of the "workflow instance context URI" for data.
*   **Debugging Tips:** Basic advice for troubleshooting.
*   **"Writing Your Own Project" Section:** Guides users on applying KCE to their problems.
*   **MVP Limitations Acknowledged:** Subtly points out areas that are simplified for MVP (e.g., provenance querying, domain ontology loading).
*   **Path Resolution:** Mentions how `script_path` is resolved.
