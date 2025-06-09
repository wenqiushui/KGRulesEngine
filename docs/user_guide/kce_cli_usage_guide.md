# KCE CLI Usage Guide

## 1. Overview

The Knowledge-CAD-Engine (KCE) Command Line Interface (CLI) is the primary tool for interacting with the KCE. It allows users to load definitions (ontologies, nodes, rules), manage the knowledge base, solve problems using the KCE Planner, and query the stored knowledge and execution logs.

This guide covers the setup, common options, and usage for each available command based on the refactored KCE architecture.

## 2. Prerequisites and Setup

*   **Python:** Python 3.8+ is required.
*   **Dependencies:** Ensure all necessary Python libraries are installed (e.g., `rdflib`, `pyyaml`, `click`, `owlrl`). If a `requirements.txt` is provided with the KCE project, install using:
    ```bash
    pip install -r requirements.txt
    ```
*   **Environment:** It's recommended to use a Python virtual environment.
*   **Running the CLI:** The CLI is invoked via `python cli/main.py ...` from the project root directory.

## 3. Global CLI Options

These options can be used with the main `kce` command group and apply to most sub-commands:

*   `--db-path <path/to/your_kce_store.sqlite>`:
    *   Specifies the path to the SQLite database file that KCE will use for its RDF store.
    *   If not provided, defaults to `kce_store.sqlite` in the directory from which the CLI is run (or relative to project root if constants are set up that way in `cli/main.py`).
*   `--in-memory`:
    *   If specified, KCE will use an in-memory RDF store. This is useful for temporary operations or testing, as no data will be persisted to disk.
    *   This option overrides `--db-path` if both are provided.
*   `--base-script-path <path/to/scripts_base_dir/>`:
    *   Provides a hint for `NodeExecutor` for locating scripts if paths in definitions are not absolute or need a specific base. However, the primary mechanism is that `DefinitionLoader` resolves `scriptPath` in YAML definitions relative to the YAML file's location, storing absolute paths in the RDF. This option can serve as a fallback or for alternative script location strategies.
*   `-v, --verbose`:
    *   Enables verbose logging output (DEBUG level). Useful for troubleshooting.
*   `--version`:
    *   Displays the KCE CLI version and exits.
*   `-h, --help`:
    *   Shows help messages for the CLI or a specific command.

## 4. Commands

### 4.1. `init-db`

Initializes or clears the KCE database and loads the core KCE ontology.

**Usage:**
```bash
python cli/main.py init-db [OPTIONS]
```

**Options:**
*   `--core-ontology-file <path/to/core_ontology.ttl>`:
    *   Specifies the path to the KCE core ontology file.
    *   Defaults to `ontologies/kce_core_ontology.ttl` relative to the project root (as defined by `DEFAULT_ONTOLOGY_DIR` in `cli/main.py`).
    *   The command will prompt for confirmation before clearing the database.

**Example:**
```bash
python cli/main.py init-db --core-ontology-file ontologies/kce_core_ontology.ttl
```
This command re-initializes the `RdfStoreManager` and `DefinitionLoader` instances in the CLI context. For file-based stores, this effectively clears the database by creating a new graph instance. For in-memory stores, it starts fresh.

### 4.2. `load-defs`

Loads KCE definitions (nodes, rules, capabilities, etc.) from YAML files within a specified directory.

**Usage:**
```bash
python cli/main.py load-defs <definitions_directory_path>
```

**Arguments:**
*   `<definitions_directory_path>`: (Required) The path to the directory containing YAML definition files. The command will recursively search for `.yaml` or `.yml` files in this directory.

**Behavior:**
*   The `DefinitionLoader` parses each YAML file.
*   It expects YAML files to contain a list of definitions or a single definition document. Each definition item should have a `kind` field (e.g., `AtomicNode`, `Rule`).
*   Relative `scriptPath` values in node definitions are resolved to absolute paths based on the location of the YAML file they are defined in. These absolute paths are then stored in the RDF knowledge base.
*   The command reports the number of successfully processed definition documents and lists any errors encountered.
*   This command does *not* automatically trigger OWL reasoning after loading. Reasoning is typically handled by the Planner or can be manually triggered if needed for specific checks via a `query` command or a dedicated `reason` command (if implemented).

**Example:**
```bash
python cli/main.py load-defs examples/elevator_panel_simplified/definitions/
```

### 4.3. `solve-problem`

Invokes the KCE Planner to solve a problem defined by a target description and an initial state.

**Usage:**
```bash
python cli/main.py solve-problem [OPTIONS]
```

**Options:**
*   `--target-desc-file <path/to/target.json>`: (Required) Path to a JSON file describing the target goal. This JSON file must contain a `sparql_ask_query` field whose value is the SPARQL ASK query defining the goal state.
*   `--initial-state-file <path/to/initial_state.json>`: (Required) Path to a JSON file describing the initial state of the problem. This JSON should ideally be in a JSON-LD format that `DefinitionLoader.load_initial_state_from_json()` can convert to RDF (see `examples/elevator_panel_simplified/params/scenario1_params.json` for an example).
*   `--run-id <custom_run_id>`: (Optional) Assigns a specific string ID for this execution run. If not provided, a UUID-based run ID will be generated.
*   `--mode <user|expert>`: (Optional) Execution mode. Defaults to `user`. (MVP Planner primarily supports `user` mode, where `expert` mode is not yet implemented).

**Behavior:**
1.  Loads the target description from the specified JSON file.
2.  Loads the initial state JSON and converts it into an RDF graph using the `DefinitionLoader`.
3.  Calls the `Planner.solve()` method, providing the target, initial state, and access to other KCE components (KnowledgeLayer, PlanExecutor, RuleEngine).
4.  The Planner attempts to find and execute a sequence of nodes and rule applications to achieve the target.
5.  Reports success or failure, along with any messages from the Planner. Verbose mode (`-v`) will show more detailed logs from the Planner and other components.

**Example:**
```bash
python cli/main.py solve-problem \
    --target-desc-file examples/elevator_panel_simplified/params/target_scenario1.json \
    --initial-state-file examples/elevator_panel_simplified/params/scenario1_params.json \
    --run-id elevator_example_run_007 -v
```

### 4.4. `query`

Executes arbitrary SPARQL queries against the KCE KnowledgeLayer.

**Usage:**
```bash
python cli/main.py query "<SPARQL_QUERY_STRING>" [OPTIONS]
python cli/main.py query <path/to/query_file.sparql> [OPTIONS]
```

**Arguments:**
*   `<sparql_query_or_file>`: (Required) Either a SPARQL query string directly, or a path to a file containing the SPARQL query.

**Options:**
*   `--format <table|json|turtle|xml|json-ld|n3|nt>`: (Optional) Specifies the output format.
    *   For `SELECT` queries: `table` (default), `json`.
    *   For `CONSTRUCT`/`DESCRIBE` queries (which return an RDF graph): `turtle` (default if an unsupported graph format is chosen), `xml`, `json-ld`, `n3`, `nt`.
    *   This option is ignored for `ASK` and Update queries.

**Behavior:**
*   Automatically detects query type (SELECT, ASK, CONSTRUCT, DESCRIBE, INSERT, DELETE, LOAD, etc.).
*   Uses `IKnowledgeLayer.execute_sparql_query()` for read queries.
*   Uses `IKnowledgeLayer.execute_sparql_update()` for update queries.
*   Formats and prints results to standard output.

**Examples:**
```bash
# SELECT query, output as table
python cli/main.py query "SELECT ?s ?p ?o WHERE {?s ?p ?o} LIMIT 10"

# SELECT query from file, output as JSON
python cli/main.py query queries/my_select_query.sparql --format json

# ASK query
python cli/main.py query "PREFIX ex: <http://example.com/ns#> ASK { ex:someInstance rdf:type ex:MyType . }"

# CONSTRUCT query, output as Turtle
python cli/main.py query "CONSTRUCT {?s ?p ?o} WHERE {?s ?p ?o ; a ex:MyType .}" --format turtle

# INSERT query
python cli/main.py query "INSERT DATA { <http://example.com/s1> <http://example.com/p1> 'hello' . }"
```

### 4.5. `show-log`

Displays RDF execution state logs for a given Run ID.

**Usage:**
```bash
python cli/main.py show-log <run_id> [OPTIONS]
```

**Arguments:**
*   `<run_id>`: (Required) The string ID of the execution run for which to display logs (e.g., `elevator_example_run_007` from the `solve-problem` example).

**Options:**
*   `--show-human-readable`, `-hr`: (Optional) If specified, also displays the content of linked human-readable JSON logs for each event, if available.

**Behavior:**
*   Queries the `KnowledgeLayer` for `kce:ExecutionStateNode` instances associated with the provided `run_id`.
*   Displays details for each state node/event in chronological order, including timestamp, event type, operation URI (if any), status, and messages.
*   If `--show-human-readable` is used, it will attempt to fetch and pretty-print the corresponding JSON log content.

**Example:**
```bash
python cli/main.py show-log elevator_example_run_007 -hr
```

## 5. Expected Directory Structure & File Formats

*   **Ontologies:** Typically in an `ontologies/` directory. Core KCE ontology (`kce_core_ontology.ttl`) and domain-specific ontologies (e.g., `elevator_panel_simplified.ttl`).
*   **Definitions:** Typically in a `definitions/` subdirectory for an example or domain (e.g., `examples/my_domain/definitions/`).
    *   `nodes.yaml`: Contains definitions for `AtomicNode`s.
    *   `rules.yaml`: Contains definitions for `Rule`s.
    *   (Other YAMLs for other definition types if supported in the future).
*   **Parameters/Initial State:** Typically in a `params/` subdirectory for an example.
    *   `my_scenario_params.json`: Initial state for a problem, ideally in JSON-LD format.
    *   `my_scenario_target.json`: Target description for the Planner, containing a `sparql_ask_query`.
*   **Scripts:** Python scripts executed by nodes are usually in a `scripts/` subdirectory. `DefinitionLoader` resolves `scriptPath` in YAML relative to the YAML file's location and stores absolute paths in the knowledge base.

This guide provides a starting point for using the KCE CLI. Refer to command-specific help (`python cli/main.py <command> --help`) for more details.
