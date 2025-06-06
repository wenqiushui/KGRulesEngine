# Knowledge-CAD-Engine (KCE) - MVP Design Specification

**Version:** 0.1
**Date:** 2023-10-27
**Authors:** [Your Name/Team Name]

## 1. Introduction

### 1.1. Purpose
This document outlines the design specifications for the Minimum Viable Product (MVP) of the Knowledge-CAD-Engine (KCE). KCE aims to be a foundational framework enabling the automation of design and calculation processes, particularly in CAD-related domains, by leveraging knowledge representation (RDF/OWL), rule-based reasoning, and a node-based workflow execution model.

The MVP focuses on demonstrating the core capabilities of KCE: defining and executing workflows composed of atomic and composite nodes, integrating external Python scripts as nodes, utilizing OWL RL reasoning, applying simple declarative rules to influence workflow execution, and recording basic provenance information.

### 1.2. Scope of MVP
The MVP will deliver:
*   A Python core library (`kce_core`) implementing the foundational logic.
*   A Command Line Interface (`kce_cli`) for interacting with the framework.
*   Support for defining nodes, rules, and workflows via YAML configuration files.
*   Execution of workflows involving external Python scripts.
*   Basic OWL RL reasoning capabilities integrated into the workflow.
*   A simple rule evaluation mechanism.
*   Support for composite nodes (sub-workflows).
*   Basic execution logging and data provenance 기록 (RDF-based).
*   Automated tests for core functionalities.
*   Example use case demonstrating the MVP's capabilities (e.g., simplified elevator panel configuration).

### 1.3. Goals of MVP
*   **Validate Core Architecture:** Prove the viability of integrating RDF/OWL, rule evaluation, and node-based execution.
*   **Demonstrate Key Features:** Showcase how KCE can automate a simple design/calculation process.
*   **Provide Foundation for Iteration:** Establish a solid codebase for future enhancements.
*   **Gather Early Feedback:** Enable initial user interaction and feedback collection.

### 1.4. Non-Goals of MVP
*   Complex graphical user interface (GUI) for workflow design or monitoring.
*   Advanced rule engine capabilities (e.g., complex conflict resolution, forward/backward chaining beyond simple triggers).
*   Sophisticated error handling and recovery mechanisms across distributed systems.
*   Advanced performance optimization for very large datasets or high-throughput scenarios.
*   Support for a wide range of external tool integration beyond Python scripts.
*   Full-fledged PROV-O compliance for provenance (a simplified model will be used).
*   Advanced security features.

## 2. System Architecture

### 2.1. Overview
KCE will consist of the following main components:

1.  **Knowledge Base (RDF Store):** Stores all definitions (ontologies, nodes, rules, workflows) and instance data (problem parameters, execution results, provenance).
    *   Backend: SQLite via `rdflib-sqlite`.
2.  **Definition Loader & Converter:** Parses YAML configuration files and transforms them into RDF triples in the Knowledge Base.
3.  **Reasoning Engine:** Utilizes `owlrl` to perform OWL RL reasoning over the RDF graph.
4.  **Execution Engine:**
    *   **Workflow Executor:** Manages the execution of defined workflows.
    *   **Node Executor:** Executes individual atomic nodes (specifically, Python scripts).
    *   **Rule Evaluator:** Assesses simple rules and triggers actions (e.g., node execution).
5.  **Provenance Logger:** Records execution metadata and data lineage into the Knowledge Base.
6.  **Command Line Interface (CLI):** Provides user interaction pTM (Point of Main Interaction).

![KCE MVP Architecture Diagram (Conceptual - Placeholder for a real diagram)](placeholder_for_architecture_diagram.png)
*(Ideally, include a simple block diagram here)*

### 2.2. Technology Stack
*   **Programming Language:** Python 3.8+
*   **RDF Handling:** `rdflib`
*   **OWL Reasoning:** `owlrl`
*   **Data Storage (RDF Backend):** SQLite (via `rdflib-sqlite` plugin for `rdflib`)
*   **Configuration File Format:** YAML (for definitions), JSON (for instance parameters)
*   **Testing Framework:** `pytest`
*   **CLI Framework:** `click`

## 3. Data Model and Ontologies

### 3.1. KCE Core Ontology (kce_core_ontology_v0.2.ttl)
A dedicated OWL/RDFS ontology will define the core concepts of KCE. Key classes and properties will include (but are not limited to):

*   **`kce:Entity`**: Base class for most KCE entities.
*   **`kce:Node`**: Abstract base class for executable units.
    *   `kce:label` (rdfs:label)
    *   `kce:description` (dcterms:description)
    *   `kce:hasInputParameter` (range: `kce:InputParameter`)
    *   `kce:hasOutputParameter` (range: `kce:OutputParameter`)
*   **`kce:AtomicNode`** (subclass of `kce:Node`): Represents a single, indivisible executable unit.
    *   `kce:hasInvocationSpec` (range: `kce:PythonScriptInvocation`)
*   **`kce:CompositeNode`** (subclass of `kce:Node`): Represents a sub-workflow.
    *   `kce:hasInternalWorkflow` (range: `kce:Workflow`)
    *   `kce:mapsInputToInternal` (describes mapping of composite node inputs to internal workflow inputs)
    *   `kce:mapsInternalToOutput` (describes mapping of internal workflow outputs to composite node outputs)
*   **`kce:Parameter`**: Abstract base for input/output parameters.
    *   `kce:parameterName` (xsd:string)
    *   `kce:mapsToRdfProperty` (rdf:Property, indicates the RDF property storing/providing the value)
    *   `kce:dataType` (rdfs:Datatype, e.g., xsd:string, xsd:integer)
    *   `kce:isRequired` (xsd:boolean, for inputs)
*   **`kce:InputParameter`** (subclass of `kce:Parameter`)
*   **`kce:OutputParameter`** (subclass of `kce:Parameter`)
*   **`kce:PythonScriptInvocation`**: Describes how to execute a Python script.
    *   `kce:scriptPath` (xsd:string)
    *   `kce:argumentPassingStyle` (e.g., "commandline")
*   **`kce:Workflow`**: Represents a sequence of steps.
    *   `kce:hasStep` (range: `kce:WorkflowStep`)
*   **`kce:WorkflowStep`**: A step in a workflow.
    *   `kce:executesNode` (range: `kce:Node`)
    *   `kce:order` (xsd:integer)
    *   `kce:nextStep` (range: `kce:WorkflowStep`, for linear MVP)
*   **`kce:Rule`**: A declarative rule.
    *   `kce:hasConditionSPARQL` (xsd:string, an ASK query)
    *   `kce:hasActionNodeURI` (xsd:anyURI, URI of the node to execute if condition is true)
    *   `kce:priority` (xsd:integer, optional for MVP)
*   **Execution Provenance (Simplified PROV-O inspired):**
    *   **`kce:ExecutionLog`**: Overall workflow execution.
        *   `kce:runId` (xsd:string)
        *   `kce:executesWorkflow` (range: `kce:Workflow`)
        *   `prov:startedAtTime`, `prov:endedAtTime`
        *   `kce:executionStatus` (e.g., "CompletedSuccess", "Failed")
    *   **`kce:NodeExecutionLog`**: Individual node execution instance.
        *   `prov:wasAssociatedWith` (range: `kce:ExecutionLog`)
        *   `kce:executesNodeInstance` (range: `kce:Node`)
        *   `prov:startedAtTime`, `prov:endedAtTime`
        *   `kce:executionStatus`
        *   `prov:used` (range: rdf:Resource, input data URI)
        *   `prov:wasGeneratedBy` (for output data, linking back to this `kce:NodeExecutionLog`)

### 3.2. Configuration Data (YAML/JSON)
*   **YAML:** Used for defining nodes, rules, and workflows. This provides a human-readable format that will be converted to RDF.
    *   Structure will map closely to the KCE Core Ontology.
*   **JSON:** Used for providing instance parameters for a specific workflow execution.

## 4. Core Components Design

### 4.1. RDF Store (`kce_core.rdf_store`)
*   **Store Manager:**
    *   Manages connection to the SQLite-backed `rdflib` graph.
    *   Provides methods to load RDF data from files (TTL, etc.) or strings.
    *   Provides methods to execute SPARQL SELECT and ASK queries.
    *   Provides methods to execute SPARQL UPDATE queries.
    *   Integrates with `owlrl` to trigger reasoning (e.g., after data loading or updates).
    *   Handles graph initialization and (optionally) clearing for tests.

### 4.2. Definition Loader (`kce_core.definitions.loader`)
*   Reads YAML files for nodes, rules, and workflows.
*   Validates the basic structure of the YAML.
*   Transforms the YAML data into RDF triples according to the KCE Core Ontology.
*   Uses the `StoreManager` to add these triples to the RDF graph.

### 4.3. Execution Engine (`kce_core.execution`)

#### 4.3.1. Node Executor (`node_executor.py`)
*   Responsible for executing `kce:AtomicNode` instances (Python scripts).
*   **Input:** Node URI, current RDF graph.
*   **Process:**
    1.  Query RDF graph for the node's `kce:InputParameter` definitions and `kce:PythonScriptInvocation` spec.
    2.  For each input parameter, retrieve its value from the RDF graph based on `kce:mapsToRdfProperty`.
    3.  Prepare command-line arguments for the Python script.
    4.  Execute the Python script using `subprocess` module.
    5.  Capture `stdout` (for primary output) and `stderr` (for errors).
    6.  If execution is successful, parse `stdout` (MVP assumes simple string or JSON parsable output).
    7.  For each `kce:OutputParameter`, store the corresponding parsed output value into the RDF graph at `kce:mapsToRdfProperty`.
*   Logs start, end, status, and any errors to the Provenance Logger.

#### 4.3.2. Rule Evaluator (`rule_evaluator.py`)
*   Responsible for evaluating `kce:Rule` instances.
*   **Input:** Current RDF graph.
*   **Process:**
    1.  Query RDF graph for all active `kce:Rule` instances.
    2.  For each rule:
        *   Execute its `kce:hasConditionSPARQL` (ASK query) against the RDF graph.
        *   If the condition is true, identify the `kce:hasActionNodeURI`.
        *   Signal the Workflow Executor to consider this action node for execution (e.g., add to a dynamic execution queue or set a flag).
*   MVP: Evaluation will occur at predefined points in the workflow (e.g., after each node execution).

#### 4.3.3. Workflow Executor (`workflow_executor.py`)
*   Responsible for orchestrating the execution of a `kce:Workflow`.
*   **Input:** Workflow URI, initial parameters (JSON), RDF graph.
*   **Process:**
    1.  Log workflow start.
    2.  Load initial parameters from JSON into the RDF graph.
    3.  Query RDF graph for the workflow's steps (`kce:WorkflowStep`) in `kce:order`.
    4.  Maintain a queue or list of nodes to execute (initially from workflow steps, potentially augmented by rules).
    5.  Iterate through nodes to execute:
        *   If the node is an `kce:AtomicNode`, invoke the `NodeExecutor`.
        *   If the node is a `kce:CompositeNode`:
            *   Retrieve its `kce:hasInternalWorkflow` URI.
            *   Handle input parameter mapping (`kce:mapsInputToInternal`) from composite node's context to internal workflow's context.
            *   Recursively call the `WorkflowExecutor` for the internal workflow.
            *   Handle output parameter mapping (`kce:mapsInternalToOutput`) from internal workflow's results to composite node's output context.
        *   After each node execution, invoke the `RuleEvaluator`.
        *   Update the execution queue based on `kce:nextStep` and rule-triggered actions.
    6.  Handle basic error propagation (if a node fails, the workflow may fail).
    7.  Log workflow end and final status.

### 4.4. Provenance Logger (`kce_core.provenance.logger`)
*   Provides methods to create and store execution log and basic provenance triples in the RDF graph.
*   Used by Workflow Executor and Node Executor.
*   Follows the simplified PROV-O inspired model defined in the KCE Core Ontology.
    *   Creates `kce:ExecutionLog` instances for workflow runs.
    *   Creates `kce:NodeExecutionLog` instances for each node invocation.
    *   Links input/output data URIs using `prov:used` and creates `prov:wasGeneratedBy` relationships (e.g., linking an output data URI to the `kce:NodeExecutionLog` that produced it).

### 4.5. Command Line Interface (`cli.main`)
*   Uses `click` framework.
*   **Commands:**
    *   `kce load-defs <yaml_dir_or_file>`: Loads definitions from YAML into the RDF store. Triggers reasoning after loading.
    *   `kce run-workflow <workflow_uri> --params <json_file_or_string>`: Executes a specified workflow with given parameters.
    *   `kce query-log [--run-id <run_id>]`: Displays execution logs (text-based for MVP).
    *   `kce query-provenance --uri <rdf_resource_uri>`: Shows basic provenance for a given RDF resource (e.g., what node generated it, what inputs it used).
    *   `kce sparql <query_string_or_file>`: (Optional utility) Executes a raw SPARQL query against the store.

## 5. Example Use Case for MVP (Simplified Elevator Panel)

*   **Goal:** Determine panel thickness, number of stiffeners, and calculate basic cost based on panel width and height.
*   **Entities:** `ElevatorPanel`, `Stiffener`.
*   **Workflow:**
    1.  **Input Node:** Takes `panelWidth` and `panelHeight` as JSON input, adds them as properties to an `ElevatorPanel` instance in RDF.
    2.  **Reasoning Step:** OWL RL rules in the domain ontology might infer `PanelType` (e.g., "LargePanel") based on dimensions.
    3.  **CalculateThicknessNode (Atomic, Python):** Takes `panelHeight`, infers `panelThickness` (e.g., if height > 2300, thickness = 1.5, else 1.3).
    4.  **DetermineStiffenersRule (Rule):**
        *   Condition: `ASK { ?panel rdf:type ex:ElevatorPanel ; ex:panelWidth ?w . FILTER(?w > 500) }`
        *   Action: Trigger `AddHighStiffenerNode`.
    5.  **AddHighStiffenerNode (Atomic, Python):** Sets `numberOfStiffeners` to 2 for the panel. (Alternative: `AddLowStiffenerNode` sets it to 1).
    6.  **CalculatePanelCostNode (Composite):**
        *   Internal Workflow:
            *   `MaterialCostNode (Atomic, Python)`: Calculates material cost based on thickness and width.
            *   `StiffenerCostNode (Atomic, Python)`: Calculates stiffener cost based on `numberOfStiffeners`.
            *   `SumCostsNode (Atomic, Python)`: Sums material and stiffener costs to get `totalPanelCost`.
        *   Output: `totalPanelCost`.
    7.  **Output Node:** Prints/logs the `ElevatorPanel` details including `panelThickness`, `numberOfStiffeners`, and `totalPanelCost`.

## 6. Testing Strategy
*   **Unit Tests (`pytest`):** For individual modules and functions (e.g., YAML loader, SPARQL query execution, node script invocation logic). Mocking external dependencies where appropriate.
*   **Integration Tests (`pytest`):**
    *   Test the full lifecycle: loading definitions, running a workflow with multiple nodes (atomic and composite), rule evaluation, provenance logging.
    *   Test CLI command functionality.
    *   Use pre-defined YAML/JSON configurations and expected RDF graph states/outputs for assertions.
*   **Test Data:** Small, well-defined RDF files, YAML/JSON configuration files stored in `tests/test_data/`.
*   **Automation:** Tests will be automated and runnable with a single command.

## 7. Directory Structure
(Refer to the previously defined directory structure in the earlier discussion)

## 8. Risks and Mitigation
*   **Complexity of RDF and OWL:** Provide clear examples and keep the MVP ontology simple.
*   **YAML to RDF Transformation Logic:** Start with a straightforward mapping; add complexity iteratively. Thoroughly test this component.
*   **Rule Evaluation Logic Nuances:** Keep MVP rule evaluation simple (direct trigger); more complex rule interactions deferred.
*   **Python Script Integration Robustness:** Define clear contracts for script inputs/outputs. Handle basic script errors.
*   **Scope Creep:** Strictly adhere to MVP features. Defer non-essential enhancements.

## 9. Future Considerations (Post-MVP)
*   Advanced rule engine integration (e.g., Drools, or more SWRL-like capabilities).
*   More complex workflow control structures (parallel execution, complex branching, loops).
*   Graphical User Interface for design and monitoring.
*   Enhanced error handling and retry mechanisms.
*   Performance optimizations for larger scale use.
*   Expanded external tool integration.
*   Full PROV-O compliance.
*   Version control for definitions within the KCE.

This MVP design specification provides a roadmap for the initial development of the Knowledge-CAD-Engine. It emphasizes core functionality to validate the concept and provide a platform for future growth.