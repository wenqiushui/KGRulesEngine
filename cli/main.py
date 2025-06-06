import click
import logging
from pathlib import Path
import sys
import json
import rdflib # For KCE/EX Namespaces and other RDF operations

# New Layer Imports from kce_core
from kce_core.interfaces import (
    IKnowledgeLayer, IDefinitionTransformationLayer, IPlanner,
    IPlanExecutor, INodeExecutor, IRuleEngine, IRuntimeStateLogger,
    TargetDescription, RDFGraph, ExecutionResult, LoadStatus # Key data structures
)
from kce_core.knowledge_layer.rdf_store.store_manager import RdfStoreManager
from kce_core.definition_transformation_layer.loader import DefinitionLoader
from kce_core.execution_layer.node_executor import NodeExecutor
from kce_core.execution_layer.runtime_state_logger import RuntimeStateLogger
from kce_core.execution_layer.plan_executor import PlanExecutor
from kce_core.planning_reasoning_core_layer.rule_engine import RuleEngine
from kce_core.planning_reasoning_core_layer.planner import Planner

# Common utilities - ensure these are available and correct in common.utils
# from kce_core.common.utils import load_json_file, to_uriref # Placeholder, actual functions might differ
from kce_core.common.utils import generate_instance_uri # Example, if needed directly

# Logger Setup (basic example, adapt if you have a central logger in utils)
kce_logger = logging.getLogger("kce_cli")
if not kce_logger.handlers: # Avoid duplicate handlers
    cli_handler = logging.StreamHandler(sys.stdout)
    # Basic formatter, can be made more sophisticated
    cli_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    cli_handler.setFormatter(cli_formatter)
    kce_logger.addHandler(cli_handler)
    kce_logger.setLevel(logging.INFO) # Default level, can be changed by -v option

# Custom Exception Classes (define here or import from a common kce_core.errors module)
class KCEError(Exception):
    """Base class for KCE specific errors."""
    pass

class DefinitionError(KCEError):
    """Error related to parsing or validity of KCE definitions."""
    pass

class RDFStoreError(KCEError):
    """Error related to RDF store operations."""
    pass

class ExecutionError(KCEError):
    """Error related to the execution of nodes or plans."""
    pass

class ConfigurationError(KCEError):
    """Error related to system configuration."""
    pass


# Version and Namespaces
def get_kce_version():
    # In future, this might read from a version file or git tag
    return "0.3.0-refactored"

KCE = rdflib.Namespace("http://kce.com/ontology/core#")
EX = rdflib.Namespace("http://example.com/ns#") # General example namespace
# Define other common RDF namespaces if used directly in CLI logic (e.g. for constructing URIs)
RDF = rdflib.RDF
RDFS = rdflib.RDFS
OWL = rdflib.OWL
XSD = rdflib.XSD
DCTERMS = rdflib.DCTERMS # Example, if needed
PROV = rdflib.PROV # Example, if needed


# --- CLI Configuration Constants (defined at module level) ---
DEFAULT_DB_PATH = "kce_store.sqlite" # Default SQLite DB file name
# Assuming this script (cli/main.py) is in 'cli_project_root/cli/main.py'
# Then project root is Path(__file__).resolve().parent.parent
PROJECT_ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ONTOLOGY_DIR = PROJECT_ROOT_DIR / "ontologies"
DEFAULT_EXAMPLES_DIR = PROJECT_ROOT_DIR / "examples" # If needed for defaults

# Ensure namespaces used in KCE are available if kce_core.common.utils doesn't re-export them all
# This is just to be safe, ideally they come from one place like common.utils or kce_core.__init__
kce_common_ns = {
    "KCE": KCE, "EX": EX, "RDF": RDF, "RDFS": RDFS, "OWL": OWL, "XSD": XSD,
    "DCTERMS": DCTERMS, "PROV": PROV
}
# --- Click Context Object (to share state between CLI commands) ---
class CliContext:
    def __init__(self):
        self.db_path: Optional[Path] = None
        # self.ontology_paths: List[Path] = [] # If needed for init
        self.verbose: bool = False
        self.base_script_path: Optional[Path] = None # For NodeExecutor script resolution

        # Attributes for new layer instances
        self.knowledge_layer: Optional[IKnowledgeLayer] = None
        self.definition_loader: Optional[IDefinitionTransformationLayer] = None
        self.runtime_logger: Optional[IRuntimeStateLogger] = None
        self.node_executor: Optional[INodeExecutor] = None
        self.rule_engine: Optional[IRuleEngine] = None
        self.plan_executor: Optional[IPlanExecutor] = None
        self.planner: Optional[IPlanner] = None

pass_cli_context = click.make_pass_decorator(CliContext, ensure=True)
# --- Main CLI Group ---
@click.group(context_settings=dict(help_option_names=['-h', '--help']))
@click.option('--db-path', default=None, type=click.Path(),
              help=f"Path to the KCE SQLite database file. Default: '{DEFAULT_DB_PATH}' in current dir if not in-memory.")
@click.option('--in-memory', is_flag=True, default=False,
              help="Use an in-memory RDF store (overrides --db-path if set).")
@click.option('--base-script-path', default=None, type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
              help="Base directory for resolving relative script paths in definitions (used by NodeExecutor).")
@click.option('-v', '--verbose', is_flag=True, help="Enable verbose logging (DEBUG level).")
@click.version_option(version=get_kce_version(), prog_name="KCE CLI Refactored")
@pass_cli_context
def cli(ctx: CliContext, db_path: Optional[str], in_memory: bool, base_script_path: Optional[str], verbose: bool):
    """Knowledge-CAD-Engine (KCE) Command Line Interface - Refactored"""

    # Logger and path setup
    ctx.verbose = verbose
    if verbose:
        kce_logger.setLevel(logging.DEBUG)
        for handler in kce_logger.handlers: handler.setLevel(logging.DEBUG)
        kce_logger.debug("Verbose logging enabled.")
    else:
        kce_logger.setLevel(logging.INFO)
        for handler in kce_logger.handlers: handler.setLevel(logging.INFO)

    actual_db_path: Optional[str] = None
    if in_memory:
        kce_logger.info("Using in-memory RDF store.")
    elif db_path:
        actual_db_path = db_path
    else:
        actual_db_path = str(PROJECT_ROOT_DIR / DEFAULT_DB_PATH) # Use PROJECT_ROOT_DIR from segment 1

    # Store Path object or None in context
    ctx.db_path = Path(actual_db_path) if actual_db_path else None

    if base_script_path:
        ctx.base_script_path = Path(base_script_path)
        kce_logger.info(f"NodeExecutor will use base script path: {ctx.base_script_path}")
    else:
        # Default base_script_path to PROJECT_ROOT_DIR/examples/scripts if available, or PROJECT_ROOT_DIR/scripts, or just PROJECT_ROOT_DIR
        # This helps NodeExecutor find scripts if not explicitly set.
        # The NodeExecutor itself has a search strategy, this sets a primary default for it.
        candidate_script_bases = [
            PROJECT_ROOT_DIR / "examples" / "scripts", # if examples dir exists
            PROJECT_ROOT_DIR / "scripts" # if a general scripts dir exists at root
        ]
        for cand_path in candidate_script_bases:
            if cand_path.exists() and cand_path.is_dir():
                ctx.base_script_path = cand_path
                kce_logger.info(f"NodeExecutor using auto-detected base script path: {ctx.base_script_path}")
                break
        if not ctx.base_script_path:
            ctx.base_script_path = PROJECT_ROOT_DIR # Fallback to project root
            kce_logger.info(f"NodeExecutor base script path defaulted to project root: {ctx.base_script_path}")

    # New component initialization logic
    try:
        # DEFAULT_ONTOLOGY_DIR should be defined in segment 1
        core_ontology_path = str(DEFAULT_ONTOLOGY_DIR / "kce_core_ontology.ttl")
        ont_files_to_load = []
        if Path(core_ontology_path).exists():
            ont_files_to_load.append(core_ontology_path)
        else:
             kce_logger.warning(f"Core KCE ontology file not found at {core_ontology_path}. Store might be missing core schema definitions.")

        # 1. Knowledge Layer
        ctx.knowledge_layer = RdfStoreManager(db_path=actual_db_path, ontology_files=ont_files_to_load)

        # 2. Definition Transformation Layer
        ctx.definition_loader = DefinitionLoader(knowledge_layer=ctx.knowledge_layer)

        # 3. RuntimeStateLogger (no direct KCE layer deps in constructor)
        ctx.runtime_logger = RuntimeStateLogger()

        # 4. NodeExecutor
        # NodeExecutor might be enhanced to take base_script_path in its constructor.
        # For now, it uses its internal logic which can be influenced by CWD or env vars.
        # If NodeExecutor is changed: # ctx.node_executor = NodeExecutor(base_script_path=ctx.base_script_path)
        ctx.node_executor = NodeExecutor() # Assuming NodeExecutor has its own script path resolution logic for now

        # 5. RuleEngine (needs RuntimeStateLogger)
        ctx.rule_engine = RuleEngine(runtime_state_logger=ctx.runtime_logger)

        # 6. PlanExecutor (needs NodeExecutor, RuntimeStateLogger, RuleEngine)
        ctx.plan_executor = PlanExecutor(
            node_executor=ctx.node_executor,
            runtime_state_logger=ctx.runtime_logger,
            rule_engine=ctx.rule_engine
        )

        # 7. Planner (needs RuntimeStateLogger in constructor)
        ctx.planner = Planner(runtime_state_logger=ctx.runtime_logger)

        kce_logger.info(f"KCE CLI initialized successfully. Store: {actual_db_path or 'in-memory'}.")

    except KCEError as e: # KCEError should be defined in segment 1
        kce_logger.error(f"Failed to initialize KCE components: {e}", exc_info=ctx.verbose)
        click.echo(f"Error: Failed to initialize KCE components: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        kce_logger.error(f"Unexpected error during KCE initialization: {e}", exc_info=True)
        click.echo(f"Unexpected Error during initialization: {e}", err=True)
        sys.exit(1)
# --- CLI Commands ---

@cli.command("init-db")
@click.option('--core-ontology-file', type=click.Path(exists=True, dir_okay=False, resolve_path=True),
              default=str(DEFAULT_ONTOLOGY_DIR / "kce_core_ontology.ttl"), # DEFAULT_ONTOLOGY_DIR from segment 1
              help="Path to the KCE core ontology file to load after clearing.")
@pass_cli_context
def init_db(ctx: CliContext, core_ontology_file: str):
    """Clears all data in the KCE store and loads the core ontology."""
    if not ctx.knowledge_layer:
        kce_logger.error("KnowledgeLayer not initialized. Cannot init-db.")
        click.echo("Error: KnowledgeLayer not initialized.", err=True)
        sys.exit(1)

    db_id = str(ctx.db_path) if ctx.db_path and ctx.db_path.name != "" else 'in-memory store' # Get path string or 'in-memory'
    try:
        click.confirm(f"This will clear all data in '{db_id}'. Continue?", abort=True)

        # Re-initialize RdfStoreManager to clear and reload ontology.
        # This is a straightforward way to ensure a clean state with the core ontology.
        core_ont_path_obj = Path(core_ontology_file)
        ont_files_to_load = [str(core_ont_path_obj)] if core_ont_path_obj.exists() else []

        if not ont_files_to_load and Path(core_ontology_file).name == "kce_core_ontology.ttl": # Check if it was the default one that's missing
             kce_logger.warning(f"Core KCE ontology file not found at {core_ontology_file}. Store will be cleared but may be missing core schema.")
        elif not ont_files_to_load: # If a custom path was given and not found (though click should prevent this)
             kce_logger.warning(f"Specified ontology file {core_ontology_file} not found. Store will be cleared but may be missing schema.")

        actual_db_path_for_reinit = str(ctx.db_path) if ctx.db_path and ctx.db_path.name != "" else None

        # Close existing connection if RdfStoreManager has a close method
        if hasattr(ctx.knowledge_layer, 'close') and callable(getattr(ctx.knowledge_layer, 'close')):
            try:
                ctx.knowledge_layer.close()
                kce_logger.info("Closed existing Knowledge Layer connection before re-initializing.")
            except Exception as close_err:
                kce_logger.warning(f"Error closing existing Knowledge Layer: {close_err}")

        # Re-assign the knowledge_layer in the context
        # This implicitly clears the old store if it's file-based and a new one is created
        # For SQLiteStore, re-opening with create=True on an existing file effectively clears it for rdflib graph.
        ctx.knowledge_layer = RdfStoreManager(
            db_path=actual_db_path_for_reinit,
            ontology_files=ont_files_to_load
        )
        # Re-initialize DTL as it depends on KL
        ctx.definition_loader = DefinitionLoader(knowledge_layer=ctx.knowledge_layer)

        click.echo(f"Store '{db_id}' effectively cleared and core ontology reloaded (if found).")
        kce_logger.info(f"Database '{db_id}' re-initialized.")

    except KCEError as e: # KCEError from segment 1
        kce_logger.error(f"Error during DB re-initialization: {e}", exc_info=ctx.verbose)
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except click.exceptions.Abort: # Catch click's Abort exception
        click.echo("Operation aborted by user.")
        kce_logger.info("init-db operation aborted by user.")
        sys.exit(0)
    except Exception as e:
        kce_logger.error(f"Unexpected error during DB re-initialization: {e}", exc_info=ctx.verbose)
        click.echo(f"Unexpected Error: {e}", err=True)
        sys.exit(1)
@cli.command("load-defs")
@click.argument('definitions_directory', # Changed from yaml_path, explicitly a directory
                type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True))
# Removed --no-reasoning option, reasoning is decoupled
@pass_cli_context
def load_defs(ctx: CliContext, definitions_directory: str): # parameter name changed
    """Loads KCE definitions (nodes, rules, etc.) from a directory of YAML files."""
    if not ctx.definition_loader or not ctx.knowledge_layer:
        kce_logger.error("DefinitionLoader or KnowledgeLayer not initialized. Cannot load definitions.")
        click.echo("Error: DefinitionLoader or KnowledgeLayer not initialized.", err=True)
        sys.exit(1)

    path_obj = Path(definitions_directory)
    click.echo(f"Loading all YAML definitions from directory: {path_obj}...")
    kce_logger.info(f"Starting definition load from directory: {path_obj}")

    try:
        # Call the new interface method from IDefinitionTransformationLayer
        load_status: LoadStatus = ctx.definition_loader.load_definitions_from_path(str(path_obj))

        loaded_count = load_status.get("loaded_definitions_count", 0)
        errors = load_status.get("errors", [])

        if loaded_count > 0:
            success_msg = f"Successfully processed {loaded_count} definition documents from directory {path_obj}."
            click.echo(click.style(success_msg, fg="green"))
            kce_logger.info(success_msg)

        if errors:
            error_summary_msg = f"Encountered {len(errors)} errors during definition loading from {path_obj}:"
            click.echo(click.style(error_summary_msg, fg="yellow"))
            kce_logger.warning(error_summary_msg)
            for err_info in errors:
                if isinstance(err_info, dict):
                    file_loc = err_info.get('file', 'N/A')
                    error_msg_detail = err_info.get('error', 'Unknown error')
                    log_line = f"  File: {file_loc}, Error: {error_msg_detail}"
                    click.echo(log_line, err=True)
                    kce_logger.error(log_line)
                else:
                    malformed_err_log = f"  Malformed error info: {err_info}"
                    click.echo(malformed_err_log, err=True)
                    kce_logger.error(malformed_err_log)
            # Consider if CLI should exit with error code if any errors occurred
            # click.echo(click.style("Definition loading completed with errors.", fg="red"), err=True)
            # sys.exit(1) # Uncomment to exit on any definition error

        if loaded_count == 0 and not errors:
            no_defs_msg = f"No definition documents found or processed in directory {path_obj}."
            click.echo(no_defs_msg)
            kce_logger.info(no_defs_msg)

        # Optional: Explicitly trigger reasoning if desired after loading definitions.
        # This is a design choice - should loading defs auto-trigger reasoning?
        # For now, it's a separate step if user wants it (e.g. via a 'reason' command or a flag here)
        # if loaded_count > 0 and ctx.knowledge_layer:
        #     click.echo("Triggering reasoning on Knowledge Layer after loading definitions...")
        #     kce_logger.info("Triggering reasoning post definition load.")
        #     ctx.knowledge_layer.trigger_reasoning()
        #     click.echo("Reasoning complete.")
        #     kce_logger.info("Reasoning post definition load complete.")

    except DefinitionError as e: # Custom DefinitionError from segment 1
        kce_logger.error(f"Definition error loading from {path_obj}: {e}", exc_info=ctx.verbose)
        click.echo(click.style(f"Definition Error: {e}", fg="red"), err=True)
        sys.exit(1)
    except KCEError as e: # General KCEError from segment 1
        kce_logger.error(f"KCE error loading definitions from {path_obj}: {e}", exc_info=ctx.verbose)
        click.echo(click.style(f"KCE Error: {e}", fg="red"), err=True)
        sys.exit(1)
    except Exception as e:
        kce_logger.critical(f"Unexpected error during definition loading from {path_obj}: {e}", exc_info=True) # Use critical for unexpected
        click.echo(click.style(f"Unexpected Error: {e}", fg="red"), err=True)
        sys.exit(1)
@cli.command("solve-problem") # Renamed from run-workflow
@click.option('--target-desc-file', type=click.Path(exists=True, dir_okay=False, resolve_path=True), required=True,
              help="Path to a JSON file describing the target goal (e.g., a SPARQL ASK query).")
@click.option('--initial-state-file', type=click.Path(exists=True, dir_okay=False, resolve_path=True), required=True,
              help="Path to a JSON file describing the initial state of the problem.")
@click.option('--run-id', 'custom_run_id', type=str, default=None, # Renamed variable to avoid clash
              help="Assign a specific run ID. If not provided, one will be generated.")
@click.option('--mode', type=click.Choice(['user', 'expert'], case_sensitive=False), default='user',
              help="Execution mode (user: fully-auto, expert: allows intervention - MVP simplified).")
@pass_cli_context
def solve_problem(ctx: CliContext, target_desc_file: str, initial_state_file: str, custom_run_id: Optional[str], mode: str):
    """Solves a problem defined by a target and an initial state using the KCE Planner."""
    if not all([ctx.planner, ctx.knowledge_layer, ctx.plan_executor, ctx.rule_engine, ctx.definition_loader, ctx.runtime_logger]):
        # Added ctx.runtime_logger to the check
        kce_logger.error("Core KCE components not initialized. Cannot solve problem. Check arguments or run init-db and load-defs.")
        click.echo("Error: Core KCE components not initialized. Check arguments or run init-db and load-defs.", err=True)
        sys.exit(1)

    import uuid # For generating run_id if not provided
    current_run_id = custom_run_id if custom_run_id else f"run_{uuid.uuid4()}"
    click.echo(f"Attempting to solve problem. Run ID: {current_run_id}")
    kce_logger.info(f"Starting solve-problem for Run ID: {current_run_id}")

    try:
        # 1. Load target description from file
        # Assuming load_json_file is available. If not, basic json.load will be used.
        try:
            from kce_core.common.utils import load_json_file # Attempt to import
            target_desc_data = load_json_file(target_desc_file)
        except ImportError:
            kce_logger.warning("kce_core.common.utils.load_json_file not found. Using basic json.load.")
            with open(target_desc_file, 'r', encoding='utf-8') as f_target:
                target_desc_data = json.load(f_target)

        if not isinstance(target_desc_data, dict) or not target_desc_data.get("sparql_ask_query"):
            err_msg_target = (f"Target description file '{target_desc_file}' must be a JSON object " + \
                             "containing at least a 'sparql_ask_query' field for the MVP planner.")
            kce_logger.error(err_msg_target)
            raise DefinitionError(err_msg_target)
        target_description: TargetDescription = target_desc_data # Type hint
        kce_logger.info(f"Loaded target description from: {target_desc_file}")

        # 2. Load initial state JSON and convert to RDF graph
        with open(initial_state_file, 'r', encoding='utf-8') as f_initial:
            initial_state_json_str = f_initial.read()

        instance_base_uri = f"http://example.com/instances/{current_run_id}/problem_data/"

        initial_state_rdf_graph: RDFGraph = ctx.definition_loader.load_initial_state_from_json(
            json_data_str=initial_state_json_str,
            base_uri=instance_base_uri
        )
        click.echo(f"Loaded initial state from '{initial_state_file}' ({len(initial_state_rdf_graph)} triples generated).")
        kce_logger.info(f"Loaded initial state from '{initial_state_file}', {len(initial_state_rdf_graph)} triples generated.")

        # 3. Call Planner.solve
        click.echo(f"Invoking KCE Planner for target defined in '{target_desc_file}'...")
        kce_logger.info(f"Invoking Planner.solve for Run ID: {current_run_id}")

        # Type hints for components passed to planner.solve to satisfy mypy if ctx attributes are Optional
        # The check at the beginning of the function ensures these are not None.
        planner_instance: IPlanner = ctx.planner # type: ignore
        kl_instance: IKnowledgeLayer = ctx.knowledge_layer # type: ignore
        pe_instance: IPlanExecutor = ctx.plan_executor # type: ignore
        re_instance: IRuleEngine = ctx.rule_engine # type: ignore

        execution_result: ExecutionResult = planner_instance.solve(
            target_description=target_description,
            initial_state_graph=initial_state_rdf_graph,
            knowledge_layer=kl_instance,
            plan_executor=pe_instance,
            rule_engine=re_instance,
            run_id=current_run_id,
            mode=mode
        )

        # 4. Process and display result
        if execution_result.get("status") == "success":
            success_final_msg = f"Problem solving successful for Run ID: {current_run_id}"
            click.echo(click.style(success_final_msg, fg="green"))
            kce_logger.info(success_final_msg)
            click.echo(f"Message: {execution_result.get('message', 'Completed.')}")
            if ctx.verbose and "plan_executed" in execution_result:
                executed_plan = execution_result["plan_executed"]
                if isinstance(executed_plan, list) and executed_plan:
                    click.echo("Executed plan steps:")
                    for i, step in enumerate(executed_plan):
                        if isinstance(step, dict):
                             click.echo(f"  {i+1}. Type: {step.get('operation_type', 'N/A')}, URI: <{step.get('operation_uri', 'N/A')}>")
                        else:
                             click.echo(f"  {i+1}. (Malformed step: {step})")
                elif executed_plan: # If it's not a list but present
                    click.echo(f"Executed plan (summary): {executed_plan}")
                else:
                    click.echo("No detailed plan steps available in result or plan was empty.")
        else:
            failure_final_msg = f"Problem solving failed for Run ID: {current_run_id}"
            click.echo(click.style(failure_final_msg, fg="red"), err=True)
            kce_logger.error(failure_final_msg)
            click.echo(f"Message: {execution_result.get('message', 'No specific error message provided.')}", err=True)
            sys.exit(1) # Exit with error code for script automation

    except DefinitionError as e:
        err_msg = f"Definition error for run_id {current_run_id}: {e}"
        kce_logger.error(err_msg, exc_info=ctx.verbose)
        click.echo(click.style(f"Definition Error: {e}", fg="red"), err=True); sys.exit(1)
    except KCEError as e:
        err_msg = f"KCE error during problem solving for run_id {current_run_id}: {e}"
        kce_logger.error(err_msg, exc_info=ctx.verbose)
        click.echo(click.style(f"Error: {e}", fg="red"), err=True); sys.exit(1)
    except FileNotFoundError as e:
        err_msg = f"File not found for run_id {current_run_id}: {e}"
        kce_logger.error(err_msg, exc_info=ctx.verbose)
        click.echo(click.style(f"File Not Found Error: {e}", fg="red"), err=True); sys.exit(1)
    except json.JSONDecodeError as e:
        err_msg = f"Invalid JSON in input file for run_id {current_run_id}: {e}"
        kce_logger.error(err_msg, exc_info=ctx.verbose)
        click.echo(click.style(f"JSON Decode Error: {e}", fg="red"), err=True); sys.exit(1)
    except Exception as e:
        err_msg = f"Unexpected error during problem solving for run_id {current_run_id}: {e}"
        kce_logger.critical(err_msg, exc_info=True) # Use critical for unexpected
        click.echo(click.style(f"Unexpected Error: {e}", fg="red"), err=True); sys.exit(1)
@cli.command("query")
@click.argument('sparql_query_or_file', type=str)
@click.option('--format', 'output_format',
              type=click.Choice(['table', 'json', 'turtle', 'xml', 'json-ld', 'n3', 'nt'], case_sensitive=False),
              default='table', help="Output format for SELECT query results or graph serialization.")
@pass_cli_context
def query_store(ctx: CliContext, sparql_query_or_file: str, output_format: str):
    """Executes a SPARQL query against the KnowledgeLayer or serializes parts of it."""
    if not ctx.knowledge_layer:
        kce_logger.error("KnowledgeLayer not initialized. Cannot execute query.")
        click.echo("Error: KnowledgeLayer not initialized.", err=True)
        sys.exit(1)

    query_str: str
    query_path = Path(sparql_query_or_file)
    if query_path.is_file() and query_path.exists(): # Check existence for clarity
        try:
            query_str = query_path.read_text(encoding='utf-8')
            kce_logger.info(f"Executing query from file: {query_path}")
        except Exception as e:
            kce_logger.error(f"Error reading query file {query_path}: {e}", exc_info=ctx.verbose)
            click.echo(f"Error reading query file {query_path}: {e}", err=True)
            sys.exit(1)
    else:
        query_str = sparql_query_or_file
        kce_logger.info(f"Executing provided SPARQL query string (first 100 chars): {query_str[:100]}...")

    query_type_test_str = query_str.strip().upper()

    try:
        if query_type_test_str.startswith("SELECT"):
            results = ctx.knowledge_layer.execute_sparql_query(query_str) # Returns List[Dict]

            if not isinstance(results, list):
                err_msg_select = f"SELECT query returned an unexpected result type: {type(results)}."
                kce_logger.error(err_msg_select)
                click.echo(err_msg_select, err=True)
                sys.exit(1)
            if not results:
                click.echo("Query returned no results.")
                return

            if output_format == 'table':
                headers = list(results[0].keys())
                col_widths = {h: len(h) for h in headers}
                string_results = []
                for row_dict in results:
                    str_row = {}
                    for h_key in headers:
                        val = row_dict.get(h_key)
                        # Handle rdflib terms for better string representation in table
                        if isinstance(val, rdflib.URIRef): val_str = f"<{val}>"
                        elif isinstance(val, rdflib.Literal):
                            val_str = f'\"{val}\"' # Basic quoting
                            if val.language: val_str += f"@{val.language}"
                            if val.datatype: val_str += f"^^<{val.datatype}>"
                        else: val_str = str(val if val is not None else '')
                        str_row[h_key] = val_str
                        if len(val_str) > col_widths[h_key]: col_widths[h_key] = len(val_str)
                    string_results.append(str_row)

                header_line = " | ".join(f"{h_val:{col_widths[h_val]}}" for h_val in headers)
                click.echo("-" * len(header_line))
                click.echo(header_line)
                click.echo("-" * len(header_line))
                for str_row_val in string_results:
                    click.echo(" | ".join(f"{str_row_val.get(h_val, ''):{col_widths[h_val]}}" for h_val in headers))
                click.echo("-" * len(header_line))

            elif output_format == 'json':
                serializable_results = []
                for row_dict in results:
                    serializable_row = {str(key): str(value) for key, value in row_dict.items()}
                    serializable_results.append(serializable_row)
                click.echo(json.dumps(serializable_results, indent=2))
            else:
                click.echo(f"Output format '{output_format}' for SELECT not directly supported for CLI pretty print. Raw results (stringified):")
                for row in results: click.echo({str(k): str(v) for k,v in row.items()})

        elif query_type_test_str.startswith("ASK"):
            result_bool = ctx.knowledge_layer.execute_sparql_query(query_str) # Returns bool
            click.echo(f"ASK Query Result: {result_bool}")

        elif query_type_test_str.startswith("CONSTRUCT") or query_type_test_str.startswith("DESCRIBE"):
            result_graph = ctx.knowledge_layer.execute_sparql_query(query_str) # Returns RDFGraph

            if not isinstance(result_graph, rdflib.Graph):
                err_msg_graph = f"Query did not return an RDF Graph as expected. Got: {type(result_graph)}"
                kce_logger.error(err_msg_graph)
                click.echo(err_msg_graph, err=True)
                sys.exit(1)

            valid_rdf_formats = ['turtle', 'xml', 'json-ld', 'n3', 'nt']
            if output_format not in valid_rdf_formats:
                warning_msg_fmt = f"Graph serialization format '{output_format}' not directly supported. Defaulting to turtle."
                click.echo(warning_msg_fmt, err=True)
                kce_logger.warning(warning_msg_fmt)
                output_format = 'turtle'

            try:
                # For json-ld, provide a basic context for better output
                # context_for_json_ld = kce_common_ns if output_format == 'json-ld' else None # kce_common_ns from segment 1
                # serialize() in rdflib 6+ does not take context directly for json-ld in this way.
                # It can be passed to the store or handled by a plugin. For basic CLI, use default serialization.
                serialized_graph = result_graph.serialize(format=output_format)
                click.echo(serialized_graph)
            except rdflib.plugin.PluginException as e:
                kce_logger.error(f"RDF serialization error for format '{output_format}': {e}", exc_info=ctx.verbose)
                click.echo(f"Error serializing graph to '{output_format}': {e}. Try 'turtle' or 'xml'.", err=True)
                sys.exit(1)

        elif any(query_type_test_str.startswith(update_kw) for update_kw in ["INSERT", "DELETE", "LOAD", "CLEAR", "DROP", "CREATE"]):
            ctx.knowledge_layer.execute_sparql_update(query_str)
            click.echo("SPARQL UPDATE/DDL operation executed successfully.")
            kce_logger.info(f"SPARQL UPDATE operation executed: {query_str[:100]}...")
        else:
            unsupported_query_msg = f"Unsupported or unrecognized SPARQL query type starting with: {query_type_test_str[:20]}..."
            kce_logger.warning(unsupported_query_msg)
            click.echo(unsupported_query_msg, err=True)
            sys.exit(1)

    except RDFStoreError as e: # RDFStoreError from segment 1
        kce_logger.error(f"Error executing query: {e}", exc_info=ctx.verbose)
        click.echo(click.style(f"Query Error: {e}", fg='red'), err=True)
        sys.exit(1)
    except Exception as e:
        kce_logger.critical(f"Unexpected error during query: {e}", exc_info=True)
        click.echo(click.style(f"Unexpected Query Error: {e}", fg='red'), err=True)
        sys.exit(1)
@cli.command("show-log")
@click.argument('run_id', type=str) # Changed from run_id_uri_str, assumes plain string ID
@click.option('--show-human-readable', '-hr', is_flag=True, default=False,
              help="Also display content of human-readable JSON logs if available.")
@pass_cli_context
def show_log(ctx: CliContext, run_id: str, show_human_readable: bool):
    """Displays RDF execution state logs for a given Run ID."""
    if not ctx.knowledge_layer:
        kce_logger.error("KnowledgeLayer not initialized. Cannot show log.")
        click.echo("Error: KnowledgeLayer not initialized.", err=True)
        sys.exit(1)

    # Determine the Run URI to query for, based on how RuntimeStateLogger constructs it
    # This base URI should ideally be a shared constant or configurable if it can change.
    # Assuming RuntimeStateLogger() is available in ctx.runtime_logger (from segment 3 init)
    base_execution_uri_for_query = ctx.runtime_logger.base_execution_uri if ctx.runtime_logger else "http://kce.com/executions/"
    run_uri_to_query = rdflib.URIRef(f"{base_execution_uri_for_query}{run_id}")

    click.echo(f"Fetching RDF execution state logs for Run ID: {run_id} (Querying for run URI <{run_uri_to_query}>)")
    kce_logger.info(f"Fetching RDF logs for run_id='{run_id}', run_uri='{run_uri_to_query}'.")

    # SPARQL query to fetch ExecutionStateNodes for the given run_uri_to_query
    log_query = f"""
    PREFIX kce: <{KCE}>
    PREFIX rdfs: <{RDFS}>
    PREFIX xsd: <{XSD}>
    SELECT ?state_node_uri ?event_type ?operation_uri ?status ?timestamp ?message ?hr_log_loc
    WHERE {{
        ?state_node_uri kce:belongsToRun <{run_uri_to_query}> .
        ?state_node_uri kce:eventType ?event_type .
        ?state_node_uri kce:status ?status .
        ?state_node_uri kce:timestamp ?timestamp .
        OPTIONAL {{ ?state_node_uri kce:triggeredByOperation ?operation_uri . }}
        OPTIONAL {{ ?state_node_uri rdfs:comment ?message . }}
        OPTIONAL {{ ?state_node_uri kce:humanReadableLogLocation ?hr_log_loc . }}
    }}
    ORDER BY ASC(?timestamp)
    """

    try:
        log_entries = ctx.knowledge_layer.execute_sparql_query(log_query)

        if not isinstance(log_entries, list):
            err_msg_log_type = f"Query for logs returned an unexpected type: {type(log_entries)}"
            kce_logger.error(err_msg_log_type)
            click.echo(err_msg_log_type, err=True)
            sys.exit(1) # Exit as this indicates a problem with KL or query

        if not log_entries:
            click.echo(f"No RDF execution state log entries found for Run ID: {run_id} (URI <{run_uri_to_query}>).", err=True)
            return

        click.echo(click.style(f"--- Execution State Log (RDF) for Run ID: {run_id} ---", bold=True))
        for i, entry in enumerate(log_entries):
            click.echo(click.style(f"Event {i+1}:", underline=True))
            click.echo(f"  State Node URI: <{entry.get('state_node_uri')}>")
            click.echo(f"  Timestamp: {entry.get('timestamp')}")
            click.echo(f"  Event Type: <{entry.get('event_type')}>")
            op_uri = entry.get('operation_uri')
            click.echo(f"  Operation URI: <{op_uri if op_uri else 'N/A'}>")
            click.echo(f"  Status: <{entry.get('status')}>")

            message = entry.get('message')
            if message:
                click.echo(f"  Message: {str(message)[:500]}{'...' if message and len(str(message)) > 500 else ''}")

            hr_log_loc_val = entry.get('hr_log_loc')
            if hr_log_loc_val:
                click.echo(f"  Human-Readable Log: {hr_log_loc_val}")
                if show_human_readable:
                    hr_content = ctx.knowledge_layer.get_human_readable_log(str(hr_log_loc_val))
                    if hr_content:
                        click.echo(click.style("    --- Human Log Content (JSON) ---", dim=True))
                        try:
                            parsed_json_log = json.loads(hr_content)
                            click.echo(json.dumps(parsed_json_log, indent=2))
                        except json.JSONDecodeError:
                            click.echo(hr_content) # Print as is if not valid JSON
                        click.echo(click.style("    --- End Human Log Content ---", dim=True))
                    else:
                        click.echo(click.style("    (Human-readable log content not found or empty)", fg="yellow"))
            click.echo("  ---")

    except RDFStoreError as e:
        err_msg_rdf_store = f"Error fetching RDF logs for run '{run_id}': {e}"
        kce_logger.error(err_msg_rdf_store, exc_info=ctx.verbose)
        click.echo(click.style(f"Error fetching RDF logs: {e}", fg='red'), err=True)
        sys.exit(1)
    except Exception as e:
        err_msg_unexpected = f"Unexpected error fetching logs for run '{run_id}': {e}"
        kce_logger.critical(err_msg_unexpected, exc_info=True)
        click.echo(click.style(f"Unexpected error fetching logs: {e}", fg='red'), err=True)
        sys.exit(1)
if __name__ == '__main__':
    # This allows running the CLI directly using `python cli/main.py`
    # For a proper installable CLI, setup.py entry_points would be used.
    cli()
