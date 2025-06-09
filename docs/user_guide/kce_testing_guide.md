# KCE Testing Guide

## 1. Introduction

This guide provides instructions on how to set up your environment and run tests for the Knowledge-CAD-Engine (KCE) project. Testing is crucial to ensure the correctness of the core components, the integration of different layers, and the overall problem-solving capabilities of the KCE.

We cover two main types of testing:
*   **Integration Tests (using Pytest):** For testing specific workflows or component interactions programmatically.
*   **CLI-based Example Tests:** For end-to-end testing by running full examples through the KCE Command Line Interface.

## 2. Environment Setup for Testing

*   **Python:** Ensure you have Python 3.8+ installed.
*   **Virtual Environment (Recommended):**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # Linux/macOS
    # .venv\Scripts\activate   # Windows
    ```
*   **Dependencies:** Install all required and development dependencies. This typically includes `pytest` in addition to KCE's core libraries (`rdflib`, `pyyaml`, `click`, `owlrl`).
    ```bash
    pip install -r requirements.txt # If requirements.txt exists
    pip install pytest # If not in requirements.txt
    ```
*   **Project Root:** All commands should generally be run from the root directory of the KCE project.

## 3. Running Integration Tests (Pytest)

The KCE project includes integration tests located in the `tests/integration/` directory. The primary integration test, `test_elevator_panel_workflow.py`, verifies the end-to-end functionality of the `elevator_panel_simplified` example.

**To run the integration tests:**

1.  **Navigate to Project Root:** Open your terminal in the root directory of the KCE project.
2.  **Ensure Files are Updated:** Make sure all relevant files (KCE core components, ontologies, example files, CLI, and the test script itself `tests/integration/test_elevator_panel_workflow.py`) are updated to their latest refactored versions as per recent development activities.
3.  **Run Pytest:**
    ```bash
    pytest
    ```
    Or, to run a specific test file with more verbose output:
    ```bash
    pytest -v -s tests/integration/test_elevator_panel_workflow.py
    ```

**Understanding `test_elevator_panel_workflow.py`:**

*   **Fixture (`kce_test_environment_components`):** This pytest fixture sets up an in-memory KCE environment for each test run. It:
    *   Initializes all refactored KCE components (`RdfStoreManager`, `DefinitionLoader`, `Planner`, etc.).
    *   Loads the core KCE ontology (`kce_core_ontology.ttl`) and the domain-specific ontology (`elevator_panel_simplified.ttl`).
    *   Loads all example definitions (nodes, rules) from `examples/elevator_panel_simplified/definitions/`.
    *   Performs OWL reasoning on the loaded knowledge base.
*   **Test Function (`test_elevator_panel_scenario_1`):**
    *   Uses the components provided by the fixture.
    *   Loads a `TargetDescription` from `examples/elevator_panel_simplified/params/target_scenario1.json`. This target defines the goal state for the Planner (typically a SPARQL ASK query).
    *   Loads the initial problem parameters from `examples/elevator_panel_simplified/params/scenario1_params.json` and converts them to an RDF graph.
    *   Invokes the `Planner.solve()` method with the target, initial state, and other necessary KCE components.
    *   Asserts that the planner reports success.
    *   Verifies the final state of the knowledge base by re-executing the target SPARQL ASK query.
    *   (Optionally) It can perform more detailed assertions by querying for specific data created during the process and comparing it against expected values (e.g., from an `expected_results.json` file).

## 4. Running CLI-based Example Tests

This involves using the KCE CLI (`python cli/main.py ...`) to run a complete example, such as the `elevator_panel_simplified` scenario. This tests the system from the user's perspective.

**Example: Running the `elevator_panel_simplified` Scenario**

**Prerequisites:**
*   All KCE files are updated (core, CLI, ontologies, examples).
*   The `merge_script.py` has been used to correctly generate/update these files if segments were provided.

**Commands (execute from project root):**

1.  **Initialize Database (Optional, for a clean test run):**
    This clears the database (e.g., `kce_store.sqlite`) and loads the core KCE ontology.
    ```bash
    python cli/main.py init-db --core-ontology-file ontologies/kce_core_ontology.ttl
    ```
    *Expected:* Confirmation message.

2.  **Load Domain Ontology & Definitions:**
    *   **Domain Ontology:** The `elevator_panel_simplified.ttl` domain ontology should be loaded. This can happen if:
        *   `kce_core_ontology.ttl` correctly `owl:imports` it and your RDF store/resolver can find it.
        *   Or, the `RdfStoreManager` (as used by the CLI) is configured to preload it (e.g., by passing it in the `ontology_files` list during initialization in `cli/main.py`).
        *   If unsure, you can attempt to load it explicitly using a SPARQL LOAD command via the CLI (path might need adjustment):
            ```bash
            # Example: python cli/main.py query "LOAD <file:./ontologies/elevator_panel_simplified.ttl>"
            ```
            (Note: Direct file loading with `LOAD` might depend on RDF store capabilities and path resolution from the store's perspective).
    *   **Example Definitions (Nodes, Rules):**
        ```bash
        python cli/main.py load-defs examples/elevator_panel_simplified/definitions/
        ```
    *Expected:* Messages indicating successful loading of definitions. Any errors in YAML files will be reported.

3.  **Solve the Problem (Run the "Workflow"):
    This command uses the Planner to achieve the goal defined in `target_scenario1.json` using the initial parameters from `scenario1_params.json`.
    ```bash
    python cli/main.py solve-problem \
        --target-desc-file examples/elevator_panel_simplified/params/target_scenario1.json \
        --initial-state-file examples/elevator_panel_simplified/params/scenario1_params.json \
        --run-id elevator_cli_test_001 \
        -v
    ```
    *Expected:*
        *   Verbose log output showing the planner's progress, node executions, rule evaluations, etc.
        *   A final message: "Problem solving successful..." or an error message if it fails.

## 5. Interpreting Test Outputs and Logs

*   **Pytest Output:**
    *   `.` indicates a passing test.
    *   `F` indicates a failed test, with a traceback and assertion error message.
    *   `E` indicates an error during test execution (not an assertion failure).
    *   Use `-s` option with pytest (`pytest -s`) to see `print()` statements and logs directly in the console.
*   **KCE CLI Output:**
    *   Success messages are usually printed to standard output.
    *   Errors are printed to standard error, often with a Python traceback if in verbose mode or if it's an unhandled exception.
*   **KCE Logs:**
    *   **`kce_logger`:** This logger (used throughout `kce_core` and `cli`) prints to the console. Verbosity is controlled by the `-v` CLI flag or logging setup in tests.
    *   **`RuntimeStateLogger` (Human-Readable Logs):**
        *   Detailed JSON logs for each execution event (node start/end, rule application) are typically stored in `data/logs/<run_id>/`. For the CLI example above, it would be `data/logs/elevator_cli_test_001/`.
        *   These logs contain actual input/output values for nodes and are invaluable for debugging.
    *   **`RuntimeStateLogger` (RDF Logs - `kce:ExecutionStateNode`):**
        *   These are stored in the main RDF knowledge base (e.g., `kce_store.sqlite`).
        *   Use the `show-log` CLI command to view them:
            ```bash
            python cli/main.py show-log elevator_cli_test_001 --show-human-readable
            ```
        *   Alternatively, use the `query` CLI command with custom SPARQL queries to inspect these RDF logs.

## 6. Common Troubleshooting Tips

*   **`FileNotFoundError`:**
    *   Check paths for ontologies, definitions, parameters, target files, and scripts.
    *   Ensure relative paths in node `scriptPath` are correctly resolved (the updated `DefinitionLoader` should make these absolute based on the YAML file's location).
    *   Verify the `--base-script-path` CLI option if used for globally relative scripts.
*   **YAML Parsing Errors (`yaml.YAMLError`):** Check the reported YAML file for syntax errors (indentation, colons, dashes, etc.).
*   **Definition Errors (`DefinitionError`):**
    *   A `kind` field might be missing or incorrect in a YAML definition.
    *   A required field (e.g., `uri`, `name`, `antecedent`/`consequent` for rules) might be missing.
    *   A URI might be malformed or use an undefined prefix.
*   **SPARQL Errors (`RDFStoreError` or errors during query execution):**
    *   Syntax errors in SPARQL queries within definitions (preconditions, effects, antecedents, consequents) or target descriptions.
    *   Prefixes used in SPARQL queries might not be defined in the query string itself or bound in the graph context.
*   **Planner Failures ("Planner could not find an executable node" or "Max planning depth reached"):
    *   Goal might be unachievable with current node definitions.
    *   Node preconditions might not be met by the initial state or subsequent states.
    *   Node `effect` definitions might not accurately describe what the node does, preventing the planner from selecting it.
    *   Circular dependencies or logic errors in how nodes/rules modify the state.
    *   Check `RuntimeStateLogger` logs for the sequence of planner decisions and node executions.
*   **Node Execution Errors (`ExecutionError`):**
    *   Python script specified in `scriptPath` not found (even with absolute paths, check file existence and permissions).
    *   Errors within the Python script itself (check its standard error output, which `NodeExecutor` should capture).
    *   Incorrect input data passed to the script, or script producing unexpected output format (not JSON, or wrong structure).
*   **Python `ImportError`:** Usually means a KCE module was not found. Check `PYTHONPATH`, virtual environment activation, or if `kce_core/__init__.py` is correctly exposing components.

By following these guidelines, you should be able to effectively test the KCE system and diagnose any issues that arise.
