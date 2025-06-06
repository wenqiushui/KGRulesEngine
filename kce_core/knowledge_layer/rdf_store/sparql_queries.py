# kce_core/rdf_store/sparql_queries.py

"""
This module contains predefined SPARQL query templates for the KCE framework.
These templates can be formatted with specific URIs or values before execution.
"""

# --- Ontology and Definition Queries ---

# Get all triples for a given subject URI
GET_ALL_TRIPLES_FOR_SUBJECT = """
SELECT ?p ?o
WHERE {{
  <{subject_uri}> ?p ?o .
}}
"""

# Get specific properties for a subject URI
GET_PROPERTIES_FOR_SUBJECT = """
SELECT ?value
WHERE {{
  <{subject_uri}> <{property_uri}> ?value .
}}
"""

# --- Node Definition Queries ---

GET_NODE_DEFINITION = """
PREFIX kce: <{kce_ns}>
PREFIX rdfs: <{rdfs_ns}>
PREFIX dcterms: <{dcterms_ns}>

SELECT ?label ?description ?invocation_spec_uri ?internal_workflow_uri
WHERE {{
  <{node_uri}> a ?node_type .
  FILTER (?node_type = kce:AtomicNode || ?node_type = kce:CompositeNode)

  OPTIONAL {{ <{node_uri}> rdfs:label ?label . }}
  OPTIONAL {{ <{node_uri}> dcterms:description ?description . }}
  OPTIONAL {{
    <{node_uri}> kce:hasInvocationSpec ?invocation_spec_uri .
    FILTER EXISTS {{ <{node_uri}> a kce:AtomicNode . }}
  }}
  OPTIONAL {{
    <{node_uri}> kce:hasInternalWorkflow ?internal_workflow_uri .
    FILTER EXISTS {{ <{node_uri}> a kce:CompositeNode . }}
  }}
}}
LIMIT 1
"""

GET_NODE_PARAMETERS = """
PREFIX kce: <{kce_ns}>

SELECT ?param_uri ?param_name ?maps_to_rdf_prop ?data_type ?is_required
WHERE {{
  <{node_uri}> <{param_direction_prop}> ?param_uri .
  ?param_uri kce:parameterName ?param_name .
  ?param_uri kce:mapsToRdfProperty ?maps_to_rdf_prop .
  OPTIONAL {{ ?param_uri kce:dataType ?data_type . }}
  OPTIONAL {{ ?param_uri kce:isRequired ?is_required . }}
}}
ORDER BY ?param_name
"""
# Note: {param_direction_prop} will be kce:hasInputParameter or kce:hasOutputParameter

GET_PYTHON_SCRIPT_INVOCATION_SPEC = """
PREFIX kce: <{kce_ns}>

SELECT ?script_path ?arg_passing_style
WHERE {{
  <{invocation_spec_uri}> a kce:PythonScriptInvocation .
  <{invocation_spec_uri}> kce:scriptPath ?script_path .
  OPTIONAL {{ <{invocation_spec_uri}> kce:argumentPassingStyle ?arg_passing_style . }}
}}
LIMIT 1
"""

GET_COMPOSITE_NODE_IO_MAPPINGS = """
PREFIX kce: <{kce_ns}>

SELECT ?map_prop ?external_param_name ?internal_param_name_or_prop_uri
WHERE {{
  <{composite_node_uri}> ?map_prop ?mapping_uri .
  # Assuming mapping_uri links to a structure that defines the mapping details
  # This part is highly dependent on how kce:mapsInputToInternal and kce:mapsInternalToOutput are modeled.
  # For MVP, let's assume a simple model:
  # <mapping_uri> kce:mapsExternalParameterName "externalName" .
  # <mapping_uri> kce:mapsToInternalParameterName "internalName" .
  # OR
  # <mapping_uri> kce:mapsToInternalProperty <internal_prop_uri> .

  # This query is a placeholder and needs to be refined based on the exact mapping ontology.
  # For a simple MVP, perhaps the mapping is directly on the CompositeNode:
  # <composite_node_uri> kce:mapsInputToInternal [
  #   kce:externalParameterName "inputX";
  #   kce:internalParameterName "workflowInputA"
  # ] .
  # This query would then need to navigate this structure.

  # For now, a simplified query assuming direct properties on the mapping resource:
  ?mapping_uri kce:externalParameterName ?external_param_name .
  OPTIONAL {{ ?mapping_uri kce:internalParameterName ?internal_param_name_or_prop_uri . }} # if mapping to param name
  OPTIONAL {{ ?mapping_uri kce:internalPropertyURI ?internal_param_name_or_prop_uri . }} # if mapping to rdf property
}}
""" # This query is complex and depends heavily on the I/O mapping model for Composite Nodes.
    # A simpler approach for MVP might be to fetch all triples of the mapping resources.

# --- Workflow Definition Queries ---

GET_WORKFLOW_DEFINITION = """
PREFIX kce: <{kce_ns}>
PREFIX rdfs: <{rdfs_ns}>

SELECT ?label ?description
WHERE {{
  <{workflow_uri}> a kce:Workflow .
  OPTIONAL {{ <{workflow_uri}> rdfs:label ?label . }}
  OPTIONAL {{ <{workflow_uri}> dcterms:description ?description . }}
}}
LIMIT 1
"""

GET_WORKFLOW_STEPS = """
PREFIX kce: <{kce_ns}>

SELECT ?step_uri ?executes_node_uri ?order ?next_step_uri
WHERE {{
  <{workflow_uri}> kce:hasStep ?step_uri .
  ?step_uri a kce:WorkflowStep .
  ?step_uri kce:executesNode ?executes_node_uri .
  OPTIONAL {{ ?step_uri kce:order ?order . }}
  OPTIONAL {{ ?step_uri kce:nextStep ?next_step_uri . }} # For linear MVP
}}
ORDER BY ASC(?order)
"""

# --- Rule Definition Queries ---

GET_ALL_ACTIVE_RULES = """
PREFIX kce: <{kce_ns}>
PREFIX rdfs: <{rdfs_ns}>

SELECT ?rule_uri ?condition_sparql ?action_node_uri ?priority
WHERE {{
  ?rule_uri a kce:Rule .
  # Add filter for active rules if such a property exists, e.g., kce:isActive true
  ?rule_uri kce:hasConditionSPARQL ?condition_sparql .
  ?rule_uri kce:hasActionNodeURI ?action_node_uri .
  OPTIONAL {{ ?rule_uri kce:priority ?priority . }}
}}
ORDER BY DESC(?priority) ?rule_uri
"""

# --- Instance Data Queries (Execution Time) ---

# Get a specific property value for an instance (subject)
# Re-use GET_PROPERTIES_FOR_SUBJECT for this.

# --- Provenance and Log Queries ---

GET_EXECUTION_LOG_DETAILS = """
PREFIX kce: <{kce_ns}>
PREFIX prov: <{prov_ns}>

SELECT ?workflow_uri ?start_time ?end_time ?status
WHERE {{
  <{run_id_uri}> a kce:ExecutionLog .
  OPTIONAL {{ <{run_id_uri}> kce:executesWorkflow ?workflow_uri . }}
  OPTIONAL {{ <{run_id_uri}> prov:startedAtTime ?start_time . }}
  OPTIONAL {{ <{run_id_uri}> prov:endedAtTime ?end_time . }}
  OPTIONAL {{ <{run_id_uri}> kce:executionStatus ?status . }}
}}
LIMIT 1
"""

GET_NODE_EXECUTION_LOGS_FOR_RUN = """
PREFIX kce: <{kce_ns}>
PREFIX prov: <{prov_ns}>

SELECT ?node_exec_log_uri ?node_uri ?start_time ?end_time ?status
WHERE {{
  ?node_exec_log_uri prov:wasAssociatedWith <{run_id_uri}> ;
                     a kce:NodeExecutionLog .
  OPTIONAL {{ ?node_exec_log_uri kce:executesNodeInstance ?node_uri . }}
  OPTIONAL {{ ?node_exec_log_uri prov:startedAtTime ?start_time . }}
  OPTIONAL {{ ?node_exec_log_uri prov:endedAtTime ?end_time . }}
  OPTIONAL {{ ?node_exec_log_uri kce:executionStatus ?status . }}
}}
ORDER BY ASC(?start_time)
"""

GET_DATA_GENERATED_BY_NODE_EXEC = """
PREFIX prov: <{prov_ns}>

SELECT ?data_uri
WHERE {{
  ?data_uri prov:wasGeneratedBy <{node_exec_log_uri}> .
}}
"""

GET_NODE_EXEC_THAT_GENERATED_DATA = """
PREFIX prov: <{prov_ns}>

SELECT ?node_exec_log_uri
WHERE {{
  <{data_uri}> prov:wasGeneratedBy ?node_exec_log_uri .
}}
LIMIT 1
"""

GET_DATA_USED_BY_NODE_EXEC = """
PREFIX prov: <{prov_ns}>

SELECT ?data_uri
WHERE {{
  <{node_exec_log_uri}> prov:used ?data_uri .
}}
"""

# --- Helper function to format queries with namespace values ---
def format_query(query_template: str, **kwargs) -> str:
    """
    Formats a SPARQL query template with provided keyword arguments.
    Automatically injects common namespace prefixes if they are not overridden in kwargs.
    """
    from kce_core.common.utils import KCE, PROV, RDF, RDFS, OWL, DCTERMS, EX, XSD_NS

    # Default namespaces for easy use in templates
    default_ns_kwargs = {
        'kce_ns': str(KCE),
        'prov_ns': str(PROV),
        'rdf_ns': str(RDF),
        'rdfs_ns': str(RDFS),
        'owl_ns': str(OWL),
        'dcterms_ns': str(DCTERMS),
        'ex_ns': str(EX),
        'xsd_ns': str(XSD_NS)
    }
    # Merge defaults with provided kwargs, giving priority to kwargs
    final_kwargs = {**default_ns_kwargs, **kwargs}
    return query_template.format(**final_kwargs)


if __name__ == '__main__':
    # Example usage of formatting (namespaces are hardcoded here for direct test)
    kce_ns_str = "http://kce.com/ontology/core#"
    rdfs_ns_str = "http://www.w3.org/2000/01/rdf-schema#"
    dcterms_ns_str = "http://purl.org/dc/terms/"

    formatted_node_def_query = format_query(
        GET_NODE_DEFINITION,
        node_uri="http://kce.com/nodes/MyNode1"
        # kce_ns, rdfs_ns, dcterms_ns will be injected by format_query
    )
    print("--- Formatted GET_NODE_DEFINITION ---")
    print(formatted_node_def_query)

    formatted_node_params_query = format_query(
        GET_NODE_PARAMETERS,
        node_uri="http://kce.com/nodes/MyNode1",
        param_direction_prop=f"{kce_ns_str}hasInputParameter"
    )
    print("\n--- Formatted GET_NODE_PARAMETERS (Input) ---")
    print(formatted_node_params_query)

    formatted_rules_query = format_query(GET_ALL_ACTIVE_RULES)
    print("\n--- Formatted GET_ALL_ACTIVE_RULES ---")
    print(formatted_rules_query)

    # Example for a query that might not need specific URI but uses namespaces
    # Assume run_id_uri is given
    run_id = "urn:uuid:12345"
    formatted_node_logs_query = format_query(
        GET_NODE_EXECUTION_LOGS_FOR_RUN,
        run_id_uri=run_id
    )
    print("\n--- Formatted GET_NODE_EXECUTION_LOGS_FOR_RUN ---")
    print(formatted_node_logs_query)