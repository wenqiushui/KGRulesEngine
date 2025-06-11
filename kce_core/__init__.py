# kce_core/__init__.py (Refactored)

import logging # Keep for basic logging types if needed elsewhere

# --- Package Information ---
__version__ = "0.3.0" # KCE Refactored version
__author__ = "KCE Development Team"
__email__ = "dev@kce.example.com"

# --- Import kce_logger directly from common.utils ---
# This makes 'from kce_core import kce_logger' possible.
from .common.utils import kce_logger

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

# Common utilities, exceptions, and namespaces (re-export from common.utils or common.exceptions)
from .common.utils import (
    # kce_logger is already imported above
    generate_instance_uri,
    get_value_from_graph,
    create_rdf_graph_from_json_ld_dict,
    graph_to_json_ld_string,
    load_json_file,
    to_uriref,
    # Namespaces (ensure these are defined in common.utils and are the rdflib.Namespace objects)
    KCE, EX, DOMAIN, RDF, RDFS, OWL, XSD, DCTERMS, PROV # Added DOMAIN
)

from .common.exceptions import (
    KCEError,
    DefinitionError,
    RDFStoreError,
    ExecutionError,
    ConfigurationError
)

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
    # Namespaces from common.utils
    "KCE", "EX", "DOMAIN", "RDF", "RDFS", "OWL", "XSD", "DCTERMS", "PROV",
    # Other key utilities from common.utils
    "generate_instance_uri", "get_value_from_graph", "create_rdf_graph_from_json_ld_dict",
    "graph_to_json_ld_string", "load_json_file", "to_uriref",
    # Package info
    "get_kce_version", "__version__",
]

