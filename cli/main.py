# cli/main.py

import click
import logging
from pathlib import Path
import sys # For sys.exit on error
from typing import Optional, List, Dict, Any # Added for type hints

# Import core KCE components made available via kce_core/__init__.py
from kce_core import (
    RdfStoreManager as StoreManager,
    DefinitionLoader,
    PlanExecutor, # Renaming to WorkflowExecutor was confusing contextually
    NodeExecutor,
    RuleEngine, # Renaming to RuleEvaluator was confusing contextually
    Planner,    # Added Planner
    RuntimeStateLogger as ProvenanceLogger,
    kce_logger,
    KCEError, DefinitionError, RDFStoreError, ExecutionError,
    get_kce_version,
    KCE, EX, # Example namespaces for parameter keys
    generate_instance_uri, create_rdf_graph_from_json_ld_dict # Added utils
)
from kce_core.common.utils import load_json_file, to_uriref, KCE_NS_STR, EX_NS_STR # Ensure to_uriref and namespaces are available
from kce_core.knowledge_layer.rdf_store import sparql_queries

# --- CLI Configuration ---
DEFAULT_DB_PATH = "kce_store.sqlite"
DEFAULT_ONTOLOGY_DIR = Path(__file__).parent.parent / "ontologies" # Assumes ontologies are at project root/ontologies
DEFAULT_EXAMPLES_DIR = Path(__file__).parent.parent / "examples" # Assumes examples are at project root/examples

# --- Click Context Object (Optional but good for sharing state) ---
class CliContext:
    def __init__(self):
        self.db_path: Optional[Path] = None
        self.store_manager: Optional[StoreManager] = None
        self.definition_loader: Optional[DefinitionLoader] = None
        self.plan_executor: Optional[PlanExecutor] = None # Renamed from workflow_executor
        self.planner: Optional[Planner] = None # Added Planner instance
        self.rule_engine: Optional[RuleEngine] = None # Added RuleEngine instance
        self.node_executor: Optional[NodeExecutor] = None # Added NodeExecutor instance
        self.provenance_logger: Optional[ProvenanceLogger] = None # Added ProvenanceLogger instance
        self.verbose: bool = False
        self.base_script_path: Optional[Path] = None

pass_cli_context = click.make_pass_decorator(CliContext, ensure=True)


# --- Main CLI Group ---
@click.group(context_settings=dict(help_option_names=['-h', '--help']))
@click.option('--db-path', default=None, type=click.Path(),
              help=f"Path to the KCE SQLite database file. Default: '{DEFAULT_DB_PATH}' in current dir if not in-memory.")
@click.option('--in-memory', is_flag=True, default=False,
              help="Use an in-memory RDF store (overrides --db-path if set).")
@click.option('--base-script-path', default=None, type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
              help="Base directory for resolving relative script paths in definitions. Default: YAML file's directory.")
@click.option('-v', '--verbose', is_flag=True, help="Enable verbose logging (DEBUG level).")
@click.version_option(version=get_kce_version(), prog_name="KCE CLI")
@pass_cli_context
def cli(ctx: CliContext, db_path: Optional[str], in_memory: bool, base_script_path: Optional[str], verbose: bool):
    """
    Knowledge-CAD-Engine (KCE) Command Line Interface.
    Manages KCE definitions, workflows, and queries.
    """
    ctx.verbose = verbose
    if verbose:
        kce_logger.setLevel(logging.DEBUG)
        for handler in kce_logger.handlers: # Ensure all handlers respect the new level
            handler.setLevel(logging.DEBUG)
        kce_logger.debug("Verbose logging enabled.")
    else:
        kce_logger.setLevel(logging.INFO) # Default to INFO
        for handler in kce_logger.handlers:
            handler.setLevel(logging.INFO)


    if in_memory:
        ctx.db_path = None
        kce_logger.info("Using in-memory RDF store.")
    elif db_path:
        ctx.db_path = Path(db_path)
    else:
        ctx.db_path = Path(DEFAULT_DB_PATH) # Default to SQLite file in current dir if not in-memory

    if base_script_path:
        ctx.base_script_path = Path(base_script_path)

    try:
        ctx.store_manager = StoreManager(db_path=ctx.db_path)
        ctx.provenance_logger = ProvenanceLogger(ctx.store_manager)
        ctx.node_executor = NodeExecutor() # NodeExecutor takes no args in constructor
        ctx.rule_engine = RuleEngine(ctx.store_manager, ctx.provenance_logger) # RuleEngine needs KL and optionally logger
        ctx.plan_executor = PlanExecutor(ctx.node_executor, ctx.provenance_logger, ctx.rule_engine)
        ctx.planner = Planner(runtime_state_logger=ctx.provenance_logger)
        ctx.definition_loader = DefinitionLoader(ctx.store_manager, base_path_for_relative_scripts=ctx.base_script_path)

    except KCEError as e:
        kce_logger.error(f"Failed to initialize KCE components: {e}", exc_info=verbose)
        click.echo(f"Error: Failed to initialize KCE components: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        kce_logger.error(f"Unexpected error during KCE initialization: {e}", exc_info=True)
        click.echo(f"Unexpected Error: {e}", err=True)
        sys.exit(1)


# --- CLI Commands ---

@cli.command("init-db")
@click.option('--load-core-ontology', is_flag=True, default=True, help="Load the KCE core ontology.")
@click.option('--ontology-file', type=click.Path(exists=True, dir_okay=False),
              default=str(DEFAULT_ONTOLOGY_DIR / "kce_core_ontology_v0.2.ttl"),
              help="Path to the KCE core ontology file (if loading).")
@pass_cli_context
def init_db(ctx: CliContext, load_core_ontology: bool, ontology_file: str):
    """Initializes or clears the KCE database and optionally loads core ontology."""
    if not ctx.store_manager:
        click.echo("Error: StoreManager not initialized. Run with proper --db-path or --in-memory.", err=True)
        sys.exit(1)
    try:
        click.confirm(f"This will clear all data in '{ctx.db_path or 'in-memory store'}'. Continue?", abort=True)
        ctx.store_manager.clear_graph()
        click.echo(f"Database '{ctx.db_path or 'in-memory store'}' cleared and initialized.")
        if load_core_ontology:
            ont_path = Path(ontology_file)
            if ont_path.exists():
                ctx.store_manager.load_rdf_file(ont_path)
                click.echo(f"Loaded core ontology from: {ont_path}")
            else:
                click.echo(f"Warning: Core ontology file not found at {ont_path}. Skipped loading.", err=True)
    except KCEError as e:
        kce_logger.error(f"Error during DB initialization: {e}", exc_info=ctx.verbose)
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command("load-defs")
@click.argument('yaml_path', type=click.Path(exists=True))
@click.option('--no-reasoning', is_flag=True, default=False, help="Disable OWL RL reasoning after loading definitions.")
@pass_cli_context
def load_defs(ctx: CliContext, yaml_path: str, no_reasoning: bool):
    """Loads KCE definitions (nodes, rules, workflows) from YAML file(s)."""
    if not ctx.definition_loader:
        click.echo("Error: DefinitionLoader not initialized.", err=True)
        sys.exit(1)

    path_obj = Path(yaml_path)
    files_to_load = []
    if path_obj.is_file() and path_obj.suffix.lower() in ['.yaml', '.yml']:
        files_to_load.append(path_obj)
    elif path_obj.is_dir():
        files_to_load.extend(path_obj.glob('*.yaml'))
        files_to_load.extend(path_obj.glob('*.yml'))

    if not files_to_load:
        click.echo(f"No YAML files found at path: {yaml_path}", err=True)
        sys.exit(1)

    click.echo(f"Found {len(files_to_load)} YAML definition file(s) to load.")
    for file_p in files_to_load:
        try:
            click.echo(f"Loading definitions from: {file_p}...")
            ctx.definition_loader.load_definitions_from_yaml(
                file_p,
                perform_reasoning_after_load=not no_reasoning
            )
            click.echo(f"Successfully loaded definitions from {file_p}.")
        except DefinitionError as e:
            kce_logger.error(f"Error loading definitions from {file_p}: {e}", exc_info=ctx.verbose)
            click.echo(f"Error in {file_p}: {e}", err=True)
            # Optionally continue or abort all
            # sys.exit(1) # Abort on first error
            click.echo(f"Skipping {file_p} due to error.", err=True) # Continue
        except KCEError as e:
            kce_logger.error(f"A KCE error occurred loading {file_p}: {e}", exc_info=ctx.verbose)
            click.echo(f"Error loading {file_p}: {e}", err=True)
            sys.exit(1)

@cli.command("run-workflow")
@click.argument('workflow_uri_str', type=str)
@click.option('--params-json', type=str, default=None,
              help="JSON string of initial parameters (e.g., '{\"ex:inputA\": 10}')")
@click.option('--params-file', type=click.Path(exists=True, dir_okay=False), default=None,
              help="Path to a JSON file containing initial parameters.")
@click.option('--context-uri', type=str, default=None,
              help="Override the instance context URI for this workflow run.")
@pass_cli_context
def run_workflow(ctx: CliContext, workflow_uri_str: str,
                 params_json: Optional[str], params_file: Optional[str],
                 context_uri: Optional[str]):
    """Executes a KCE workflow using the Planner."""
    if not all([ctx.planner, ctx.store_manager, ctx.plan_executor, ctx.rule_engine, ctx.provenance_logger]):
        click.echo("Error: Core KCE components (Planner, StoreManager, PlanExecutor, RuleEngine, ProvenanceLogger) not initialized.", err=True)
        sys.exit(1)

    workflow_uri_rdf = to_uriref(workflow_uri_str, base_ns=EX) # Assume EX if no prefix
    if not workflow_uri_rdf:
        click.echo(f"Error: Invalid workflow URI: {workflow_uri_str}", err=True)
        sys.exit(1)

    # Determine Run ID (Instance Context URI)
    run_id_uri: rdflib.URIRef
    if context_uri:
        run_id_uri_temp = to_uriref(context_uri, base_ns=KCE["run/"]) # Example base for runs
        if not run_id_uri_temp:
            click.echo(f"Error: Invalid context URI: {context_uri}", err=True)
            sys.exit(1)
        run_id_uri = run_id_uri_temp
        click.echo(f"Using explicit Run ID (Context URI): <{run_id_uri}>")
    else:
        run_id_uri = generate_instance_uri(KCE_NS_STR + "run/", "workflow_instance")
        click.echo(f"Generated Run ID (Context URI): <{run_id_uri}>")

    # Load parameters
    params_dict: Dict[str, Any] = {}
    if params_file:
        if params_json:
            click.echo("Warning: Both --params-json and --params-file provided. Using --params-file.", err=True)
        try:
            with open(params_file, 'r') as f:
                actual_params_json_str = f.read()
        except Exception as e:
            click.echo(f"Error reading params file {params_file}: {e}", err=True)
            sys.exit(1)
    elif params_json:
        try:
            params_dict = json.loads(params_json)
        except json.JSONDecodeError as e:
            click.echo(f"Error decoding --params-json: {e}", err=True)
            sys.exit(1)

    # Construct initial_state_graph
    # Base JSON-LD structure for the problem instance
    json_ld_data: Dict[str, Any] = {
        "@context": {
            "kce": KCE_NS_STR,
            "ex": EX_NS_STR
            # TODO: Dynamically add prefixes from params_dict keys if needed
        },
        "@id": str(run_id_uri),
        "@type": "kce:ProblemInstance"
    }
    # Merge parameters into the JSON-LD structure
    # Ensure parameter keys are valid CURIEs or full URIs for JSON-LD context or direct use
    for k, v in params_dict.items():
        json_ld_data[k] = v # Assumes keys in params_dict are suitable for JSON-LD

    initial_state_graph = create_rdf_graph_from_json_ld_dict(json_ld_data, default_base_ns_str=str(KCE))
    click.echo(f"Initial state graph created with {len(initial_state_graph)} triples for Run ID <{run_id_uri}>.")
    if ctx.verbose:
        click.echo("Initial state graph (Turtle):")
        click.echo(initial_state_graph.serialize(format="turtle"))

    # Retrieve TargetDescription for the workflow
    # This assumes the workflow definition links to a TargetDescription via kce:hasTargetDescription
    # And that TargetDescription has a kce:hasSparqlAskQuery.
    target_query_sparql = f"""
        PREFIX kce: <{KCE_NS_STR}>
        SELECT ?ask_query
        WHERE {{
            <{workflow_uri_rdf}> kce:hasTargetDescription ?target_desc_uri .
            ?target_desc_uri kce:hasSparqlAskQuery ?ask_query .
        }}
        LIMIT 1
    """
    try:
        target_results = ctx.store_manager.query(target_query_sparql)
        if not target_results or not isinstance(target_results, list) or not target_results[0].get('ask_query'):
            click.echo(f"Error: Could not retrieve SPARQL ASK query for target description of workflow <{workflow_uri_rdf}>.", err=True)
            sys.exit(1)

        ask_query_str = str(target_results[0]['ask_query'])
        target_description: Dict[str, str] = {"sparql_ask_query": ask_query_str}
        click.echo(f"Target for workflow <{workflow_uri_rdf}>: ASK query retrieved.")
        if ctx.verbose:
            click.echo(f"Target ASK query: {ask_query_str}")

    except KCEError as e:
        kce_logger.error(f"Error retrieving target description for workflow <{workflow_uri_rdf}>: {e}", exc_info=ctx.verbose)
        click.echo(f"Error retrieving target: {e}", err=True)
        sys.exit(1)

    click.echo(f"Attempting to run workflow: <{workflow_uri_rdf}> with Planner...")

    try:
        # Ensure all components are not None before calling solve
        if not ctx.planner or not ctx.store_manager or not ctx.plan_executor or not ctx.rule_engine:
             click.echo("Critical Error: One or more KCE components are None before calling Planner.solve().", err=True)
             sys.exit(1)

        result: ExecutionResult = ctx.planner.solve(
            target_description=target_description,
            initial_state_graph=initial_state_graph,
            knowledge_layer=ctx.store_manager, # StoreManager acts as IKnowledgeLayer
            plan_executor=ctx.plan_executor,
            rule_engine=ctx.rule_engine,
            run_id=str(run_id_uri),
            mode="auto" # Default mode
        )

        if result.get("status") == "success":
            click.echo(click.style(f"Workflow <{workflow_uri_rdf}> completed successfully. Run ID: <{run_id_uri}>", fg="green"))
            if ctx.verbose and result.get("plan_executed"):
                click.echo("Plan Executed:")
                for i, step in enumerate(result["plan_executed"]):
                    click.echo(f"  Step {i+1}: Type='{step.get('operation_type')}', URI='{step.get('operation_uri')}'")
        else:
            click.echo(click.style(f"Workflow <{workflow_uri_rdf}> failed. Run ID: <{run_id_uri}>. Message: {result.get('message', 'No message')}", fg="red"), err=True)
            if ctx.verbose and result.get("plan_executed"):
                click.echo("Partial Plan Executed before failure:")
                for i, step in enumerate(result["plan_executed"]):
                    click.echo(f"  Step {i+1}: Type='{step.get('operation_type')}', URI='{step.get('operation_uri')}'")
            sys.exit(1) # Exit with error code if workflow failed

    except KCEError as e:
        kce_logger.error(f"Error running workflow <{workflow_uri_rdf}> with Planner: {e}", exc_info=ctx.verbose)
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e: # Catch any unexpected errors during solve
        kce_logger.error(f"Unexpected error running workflow <{workflow_uri_rdf}> with Planner: {e}", exc_info=True)
        click.echo(f"Unexpected Error: {e}", err=True)
        sys.exit(1)


@cli.command("query")
@click.argument('sparql_query_or_file', type=str)
@click.option('--format', 'output_format', type=click.Choice(['table', 'csv', 'json', 'xml', 'json-ld', 'turtle', 'n3'], case_sensitive=False), # Added json-ld
              default='table', help="Output format for SELECT query results or graph serialization.")
@pass_cli_context
def query_store(ctx: CliContext, sparql_query_or_file: str, output_format: str):
    """Executes a SPARQL query or serializes the graph."""
    if not ctx.store_manager:
        click.echo("Error: StoreManager not initialized.", err=True)
        sys.exit(1)

    query_str: str
    query_path = Path(sparql_query_or_file)
    if query_path.is_file():
        try:
            query_str = query_path.read_text()
            click.echo(f"Executing query from file: {query_path}")
        except Exception as e:
            click.echo(f"Error reading query file {query_path}: {e}", err=True)
            sys.exit(1)
    else:
        query_str = sparql_query_or_file
        click.echo("Executing provided SPARQL query string.")

    query_type_test_str = query_str.strip().upper()

    try:
        if query_type_test_str.startswith("SELECT"):
            results = ctx.store_manager.query(query_str)
            if not results:
                click.echo("Query returned no results.")
                return

            if output_format == 'table':
                # Simple table print
                if results:
                    headers = list(results[0].keys())
                    click.echo("-" * (sum(len(h) for h in headers) + len(headers) * 3 -1)) # Dynamic width
                    click.echo(" | ".join(headers))
                    click.echo("-" * (sum(len(h) for h in headers) + len(headers) * 3 -1))
                    for row in results:
                        click.echo(" | ".join(str(row.get(h, '')) for h in headers))
                    click.echo("-" * (sum(len(h) for h in headers) + len(headers) * 3 -1))
            elif output_format == 'json':
                # Convert RDFNode to string for simple JSON output
                json_results = [{k: str(v) for k, v in row.items()} for row in results]
                click.echo(json.dumps(json_results, indent=2))
            # Add other formats (csv, xml) as needed, potentially using rdflib's query result serialization
            else:
                click.echo(f"Output format '{output_format}' for SELECT not fully implemented for CLI. Raw results:")
                for row in results:
                    click.echo(row)

        elif query_type_test_str.startswith("ASK"):
            result = ctx.store_manager.ask(query_str)
            click.echo(f"ASK Query Result: {result}")

        elif query_type_test_str.startswith("CONSTRUCT") or query_type_test_str.startswith("DESCRIBE"):
            result_graph = ctx.store_manager.graph.query(query_str)
            # Supported formats for rdflib's serialize: xml, n3, turtle, nt, pretty-xml, trix, rdfa, json-ld
            supported_graph_formats = ['turtle', 'xml', 'json-ld', 'n3', 'nt', 'pretty-xml', 'trix']
            if output_format not in supported_graph_formats:
                click.echo(f"Unsupported graph serialization format '{output_format}'. Defaulting to turtle.")
                output_format = 'turtle'

            # For json-ld, provide a basic context map from graph namespaces
            extra_args = {}
            if output_format == 'json-ld':
                json_ld_context = {pfx: str(ns_uri) for pfx, ns_uri in ctx.store_manager.graph.namespaces()}
                extra_args['context'] = json_ld_context
                extra_args['indent'] = 2 # Make it readable

            serialized_graph = result_graph.serialize(format=output_format, **extra_args)
            click.echo(serialized_graph)
        elif query_type_test_str.startswith("INSERT") or query_type_test_str.startswith("DELETE"):
            ctx.store_manager.update(query_str)
            click.echo("SPARQL UPDATE executed successfully.")
        else:
            click.echo("Unknown query type. Supported: SELECT, ASK, CONSTRUCT, DESCRIBE, INSERT, DELETE.", err=True)
            sys.exit(1)

    except RDFStoreError as e:
        kce_logger.error(f"Error executing query: {e}", exc_info=ctx.verbose)
        click.echo(f"Query Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        kce_logger.error(f"Unexpected error during query: {e}", exc_info=True)
        click.echo(f"Unexpected Query Error: {e}", err=True)
        sys.exit(1)

@cli.command("show-log")
@click.argument('run_id_uri_str', type=str)
@pass_cli_context
def show_log(ctx: CliContext, run_id_uri_str: str):
    """Shows execution log details for a given workflow run ID URI."""
    if not ctx.store_manager:
        click.echo("Error: StoreManager not initialized.", err=True)
        sys.exit(1)

    run_id_uri = to_uriref(run_id_uri_str, base_ns=KCE["run/"]) # Assume KCE["run/"] if no prefix

    click.echo(f"Fetching logs for Run ID: <{run_id_uri}>")

    # Get main execution log
    exec_log_q = sparql_queries.format_query(sparql_queries.GET_EXECUTION_LOG_DETAILS, run_id_uri=str(run_id_uri))
    exec_log_res = ctx.store_manager.query(exec_log_q)
    if not exec_log_res:
        click.echo(f"No execution log found for Run ID <{run_id_uri}>.", err=True)
        return

    log = exec_log_res[0]
    click.echo("\n--- Workflow Execution Log ---")
    click.echo(f"  Run ID: <{run_id_uri}>")
    click.echo(f"  Workflow: <{log.get('workflow_uri')}>")
    click.echo(f"  Status: {log.get('status')}")
    click.echo(f"  Started: {log.get('start_time')}")
    click.echo(f"  Ended: {log.get('end_time')}")

    # Get node execution logs for this run
    node_logs_q = sparql_queries.format_query(sparql_queries.GET_NODE_EXECUTION_LOGS_FOR_RUN, run_id_uri=str(run_id_uri))
    node_logs_res = ctx.store_manager.query(node_logs_q)

    if node_logs_res:
        click.echo("\n--- Node Execution Logs ---")
        for nlog in node_logs_res:
            click.echo(f"  Node Log URI: <{nlog.get('node_exec_log_uri')}>")
            click.echo(f"    Node: <{nlog.get('node_uri')}>")
            click.echo(f"    Status: {nlog.get('status')}")
            click.echo(f"    Started: {nlog.get('start_time')}")
            click.echo(f"    Ended: {nlog.get('end_time')}")
            # Fetch and display error message if present
            error_msg = ctx.store_manager.get_single_property_value(nlog.get('node_exec_log_uri'), KCE.hasErrorMessage)
            if error_msg:
                click.echo(click.style(f"    Error: {error_msg}", fg="red"))
            click.echo("    ---")
    else:
        click.echo("  No node execution logs found for this run.")

    # TODO: Add provenance query display if time permits for MVP


if __name__ == '__main__':
    # This allows running the CLI directly using `python -m cli.main` (if kce_core is in PYTHONPATH)
    # or `python path/to/cli/main.py` (if run from project root or kce_core is installed)
    # For a proper installable CLI, use setup.py entry_points.
    cli()