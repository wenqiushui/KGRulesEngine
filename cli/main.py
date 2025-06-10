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
    PlanExecutor as WorkflowExecutor,      # Correct: Alias PlanExecutor
    NodeExecutor,
    RuleEngine as RuleEvaluator,          # Correct: Alias RuleEngine
    RuntimeStateLogger as ProvenanceLogger, # Correct: Alias RuntimeStateLogger
    # sparql_queries, # This was incorrect, imported below directly
    kce_logger,
    KCEError, DefinitionError, RDFStoreError, ExecutionError,
    get_kce_version,
    KCE, EX # Example namespaces for parameter keys
)
from kce_core.common.utils import load_json_file # load_json_string is not defined in utils.py
from kce_core.knowledge_layer.rdf_store import sparql_queries # Corrected import for sparql_queries

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
        self.workflow_executor: Optional[WorkflowExecutor] = None
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
        # Initialize other core components that depend on store_manager
        prov_logger = ProvenanceLogger(ctx.store_manager)
        node_exec = NodeExecutor(ctx.store_manager, prov_logger)
        rule_eval = RuleEvaluator(ctx.store_manager, prov_logger) # Pass prov_logger here

        ctx.definition_loader = DefinitionLoader(ctx.store_manager, base_path_for_relative_scripts=ctx.base_script_path)
        ctx.workflow_executor = WorkflowExecutor(ctx.store_manager, node_exec, rule_eval, prov_logger)

    except KCEError as e:
        kce_logger.error(f"Failed to initialize KCE components: {e}")
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
    """Executes a KCE workflow."""
    if not ctx.workflow_executor:
        click.echo("Error: WorkflowExecutor not initialized.", err=True)
        sys.exit(1)

    workflow_uri = to_uriref(workflow_uri_str, base_ns=EX) # Assume EX if no prefix

    actual_params_json_str: Optional[str] = None
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
        actual_params_json_str = params_json

    context_uri_obj = to_uriref(context_uri, base_ns=EX) if context_uri else None

    click.echo(f"Attempting to run workflow: <{workflow_uri}>")
    if actual_params_json_str:
        click.echo(f"With parameters: {actual_params_json_str[:200]}{'...' if actual_params_json_str and len(actual_params_json_str) > 200 else ''}")
    if context_uri_obj:
        click.echo(f"Using explicit context URI: <{context_uri_obj}>")

    try:
        success = ctx.workflow_executor.execute_workflow(
            workflow_uri,
            initial_parameters_json=actual_params_json_str,
            instance_context_uri_override=context_uri_obj
        )
        if success:
            click.echo(click.style(f"Workflow <{workflow_uri}> completed successfully.", fg="green"))
        else:
            click.echo(click.style(f"Workflow <{workflow_uri}> failed.", fg="red"), err=True)
            sys.exit(1) # Exit with error code if workflow failed
    except KCEError as e:
        kce_logger.error(f"Error running workflow <{workflow_uri}>: {e}", exc_info=ctx.verbose)
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command("query")
@click.argument('sparql_query_or_file', type=str)
@click.option('--format', 'output_format', type=click.Choice(['table', 'csv', 'json', 'xml', 'turtle'], case_sensitive=False),
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
            # These return a new graph. Serialize it.
            result_graph = ctx.store_manager.graph.query(query_str) # rdflib query returns a ResultGraph
            if output_format not in ['turtle', 'xml', 'json-ld', 'n3']: # Common graph formats
                click.echo(f"Unsupported graph serialization format '{output_format}'. Defaulting to turtle.")
                output_format = 'turtle'
            serialized_graph = result_graph.serialize(format=output_format)
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
    # This allows running the CLI directly using `python -m kce_core.cli.main`
    # or `python path/to/cli/main.py`
    # For a proper installable CLI, use setup.py entry_points.
    cli()