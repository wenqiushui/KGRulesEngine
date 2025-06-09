# kce_core/__init__.py (Refactored)

import logging

# --- Package Information ---
__version__ = "0.3.0-refactored" # KCE Refactored version
__author__ = "KCE Development Team"
__email__ = "dev@kce.example.com"

# --- Setup a package-level logger ---
# This logger can be used by all submodules within kce_core.
# The CLI (or other applications using kce_core) can then configure handlers for this logger.
kce_logger = logging.getLogger('kce_core')
if not kce_logger.handlers:
    # Add a NullHandler by default to prevent "No handler found" warnings
    # if the library user hasn't configured logging.
    kce_logger.addHandler(logging.NullHandler())
# Default level for the library logger. Applications can override this.
# kce_logger.setLevel(logging.WARNING) # Or logging.INFO, or let app decide

# --- Expose Key Interfaces and Classes for easier import ---

# Interfaces
from .interfaces import (
    IKnowledgeLayer,
    IDefinitionTransformationLayer,
    IPlanner,
    IPlanExecutor,
    INodeExecutor,
    IRuleEngine,
    IRuntimeStateLogger,
    # Data structures/types if they are part of the public API
    TargetDescription,
    RDFGraph,
    ExecutionResult,
    LoadStatus,
    ExecutionPlan
)

# Concrete Implementations (optional, but often convenient for users)
from .knowledge_layer.rdf_store.store_manager import RdfStoreManager
from .definition_transformation_layer.loader import DefinitionLoader
from .execution_layer.node_executor import NodeExecutor
from .execution_layer.runtime_state_logger import RuntimeStateLogger
from .execution_layer.plan_executor import PlanExecutor
from .planning_reasoning_core_layer.rule_engine import RuleEngine
from .planning_reasoning_core_layer.planner import Planner

# Common utilities, exceptions, and namespaces (re-export from common)
try:
    from .common.utils import (
        generate_instance_uri, # Example utility
        get_value_from_graph,
        create_rdf_graph_from_json_ld_dict,
        graph_to_json_ld_string,
        # Namespaces (ensure these are defined in common.utils and are the rdflib.Namespace objects)
        KCE, EX, RDF, RDFS, OWL, XSD, DCTERMS, PROV # Assuming these are exported by common.utils
    )
except ImportError as _e_utils:
    kce_logger.warning(f"Could not import all common utilities: {_e_utils}")

try:
    from .common.exceptions import (
        KCEError,
        DefinitionError,
        RDFStoreError,
        ExecutionError,
        ConfigurationError
    )
except ImportError as _e_exceptions:
    kce_logger.warning(f"Could not import common exceptions: {_e_exceptions}. Defining fallbacks.")
    # Basic fallback exceptions if common.exceptions module is not found
    class KCEError(Exception): pass
    class DefinitionError(KCEError): pass
    class RDFStoreError(KCEError): pass
    class ExecutionError(KCEError): pass
    class ConfigurationError(KCEError): pass

# --- Get KCE version ---
def get_kce_version() -> str:
    """Returns the current version of the KCE package."""
    return __version__

# --- __all__ list for 'from kce_core import *' ---
__all__ = [
    # Logger
    "kce_logger",
    # Exceptions
    "KCEError", "DefinitionError", "RDFStoreError", "ExecutionError", "ConfigurationError",
    # Core Interfaces
    "IKnowledgeLayer", "IDefinitionTransformationLayer", "IPlanner",
    "IPlanExecutor", "INodeExecutor", "IRuleEngine", "IRuntimeStateLogger",
    # Concrete Implementations (if exposing directly)
    "RdfStoreManager", "DefinitionLoader", "NodeExecutor", "RuntimeStateLogger",
    "PlanExecutor", "RuleEngine", "Planner",
    # Data types from interfaces (if public)
    "TargetDescription", "RDFGraph", "ExecutionResult", "LoadStatus", "ExecutionPlan",
    # Namespaces (if re-exported and available)
    "KCE", "EX", "RDF", "RDFS", "OWL", "XSD", "DCTERMS", "PROV",
    # Key utilities (if re-exported and available)
    "generate_instance_uri", "get_value_from_graph", "create_rdf_graph_from_json_ld_dict", "graph_to_json_ld_string",
    # Package info
    "get_kce_version", "__version__",
]
