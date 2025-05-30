from rdflib import Graph, URIRef, Literal, Namespace, RDF, RDFS
from owlrl import DeductiveClosure, OWLRL_Semantics
import re
import math # Ensure math is imported

class GraphPatternEngine:
    def __init__(self):
        self.knowledge_graph = Graph()
        self.ONT_NS = Namespace("http://example.com/ontology#")
        self.RULE_NS = Namespace("http://example.com/rules#")
        self.TMPL_NS = Namespace("http://example.com/templates#")
        
        self.knowledge_graph.bind("ont", self.ONT_NS)
        self.knowledge_graph.bind("rule", self.RULE_NS)
        self.knowledge_graph.bind("tmpl", self.TMPL_NS)
        self.knowledge_graph.bind("rdfs", RDFS) 
        self.knowledge_graph.bind("", self.ONT_NS) 
        
        self.context_manager = ContextManager()
        # Pass all relevant namespaces to RuleProcessor
        self.rule_processor = RuleProcessor(
            self.knowledge_graph, 
            self.context_manager, 
            {'ont': self.ONT_NS, '': self.ONT_NS, 'rdfs':RDFS, 'rule':self.RULE_NS, 'tmpl':self.TMPL_NS}
        )
        self.template_executor = TemplateExecutor(
            self.knowledge_graph, 
            self.context_manager, 
            self.rule_processor, 
            self.ONT_NS, # Pass ONT_NS separately if needed by TemplateExecutor for its own logic
            {'ont': self.ONT_NS, '': self.ONT_NS, 'rdfs':RDFS, 'rule':self.RULE_NS, 'tmpl':self.TMPL_NS} # Pass full init_ns_map
        )

    def load_ontology(self, ttl_file):
        self.knowledge_graph.parse(ttl_file, format="turtle")
        DeductiveClosure(OWLRL_Semantics).expand(self.knowledge_graph)

    def load_rules(self, ttl_file):
        self.knowledge_graph.parse(ttl_file, format="turtle")

    def load_templates(self, ttl_file):
        self.knowledge_graph.parse(ttl_file, format="turtle")

    def set_context(self, context_dict):
        self.context_manager.set_context(context_dict)

    def apply_rules(self):
        # Define init_ns consistently for all queries that might need it
        init_ns_map = {'ont': self.ONT_NS, '': self.ONT_NS, 'rdfs':RDFS, 'rule':self.RULE_NS, 'tmpl':self.TMPL_NS}
        rules_query_str = """
            SELECT ?rule ?condition ?action WHERE {
                ?rule a ont:Rule ; ont:condition ?condition ; ont:action ?action .
                OPTIONAL { ?rule ont:priority ?prio . }
            } ORDER BY DESC(?prio)
        """
        rules = self.knowledge_graph.query(rules_query_str, initNs=init_ns_map)
        
        for rule_row in rules: 
            rule, condition, action = rule_row[0], rule_row[1], rule_row[2]
            if self.rule_processor.evaluate_condition(condition):
                self.rule_processor.execute_action(action)

    def match_template(self, problem_type):
        problem_uri = URIRef(problem_type)
        init_ns_map = {'ont': self.ONT_NS, '': self.ONT_NS} # Only ont and default needed for this specific query
        query = f"""
            SELECT ?template WHERE {{
                ?template a ont:Template ; ont:problemType <{problem_uri}> ; ont:available true .
            }} ORDER BY DESC(ont:priority) LIMIT 1
        """
        result = list(self.knowledge_graph.query(query, initNs=init_ns_map))
        return result[0][0] if result else None

    def execute_template(self, template_uri):
        return self.template_executor.execute(template_uri)

    def query(self, problem_type, params=None):
        if params: self.context_manager.update_context(params)
        self.apply_rules() 
        template_uri = self.match_template(problem_type)
        if not template_uri:
            # Attempt to clean graph to ensure next test run is clean if this was an unexpected state.
            # self.knowledge_graph.remove((None, None, None)) # This might be too drastic or cause issues.
            raise ValueError(f"No template found for problem type: {problem_type}")
        
        execution_result = self.template_executor.execute(template_uri)
        
        # This simplified result retrieval assumes the final phase's result (a list from SELECT GROUP_CONCAT)
        # is what's needed by testCore.py's parsing logic.
        if isinstance(execution_result, list) and execution_result and isinstance(execution_result[0], tuple) and len(execution_result[0]) > 0 and isinstance(execution_result[0][0], Literal):
            key_name = "unknown"
            if "JointGeneration" in problem_type: key_name = "joints"
            elif "DimensionCalculation" in problem_type: key_name = "dimensions"
            elif "CostCalculation" in problem_type: key_name = "costs"
            # testCore.py expects: result["_:result"]["joints"]
            # The Literal contains the string that will be parsed as JSON by testCore.py
            return {"_:result": {key_name: str(execution_result[0][0])}}
        
        # Fallback or if the structure is different (e.g. from a CONSTRUCT directly)
        # This part is highly speculative and depends on how results are structured if not a direct SELECT (GROUP_CONCAT)
        # For now, returning an empty dict if the specific format above isn't matched.
        print(f"Warning: Unexpected result format from template execution: {execution_result}")
        return {}


class ContextManager:
    def __init__(self): self.context = {}
    def set_context(self, context_dict): self.context = context_dict.copy()
    def update_context(self, updates): self.context.update(updates)
    def resolve_variable(self, path):
        if '.' in path: 
            parts = path.split('.')
            current = self.context
            for part in parts:
                if isinstance(current, dict) and part in current: current = current[part]
                else: raise KeyError(f"Context variable {part} not found in {current} from path {path}") # More info
            return current
        elif path in self.context: return self.context[path]
        else: raise KeyError(f"Context variable not found: {path}")

class RuleProcessor:
    def __init__(self, graph, context_manager, init_ns_map): 
        self.graph = graph
        self.context_manager = context_manager
        self.INIT_NS = init_ns_map

    def _substitute_context_vars_sparql(self, query_string):
        variables = re.findall(r'\$context\.([a-zA-Z0-9_.]+)', query_string)
        processed_query = query_string
        for var_path in set(variables):
            try:
                value = self.context_manager.resolve_variable(var_path)
                if isinstance(value, str):
                    is_uri_like = value.startswith("http://") or value.startswith("<")
                    is_prefixed = False
                    if not is_uri_like and ':' in value:
                        prefix = value.split(':')[0]
                        # Check against the graph's known namespaces
                        if prefix in [p for p, _ in self.graph.namespaces()]:
                           is_prefixed = True
                    
                    if is_uri_like or is_prefixed:
                        processed_query = processed_query.replace(f"$context.{var_path}", value)
                    else:
                        processed_query = processed_query.replace(f"$context.{var_path}", f'"{value}"')

                elif isinstance(value, URIRef): processed_query = processed_query.replace(f"$context.{var_path}", f"<{str(value)}>")
                elif isinstance(value, Literal): processed_query = processed_query.replace(f"$context.{var_path}", value.n3())
                else: processed_query = processed_query.replace(f"$context.{var_path}", str(value))
            except KeyError as e: 
                print(f"Warning: Context variable $context.{var_path} not found for SPARQL substitution: {e}")
        return processed_query

    def evaluate_condition(self, condition_str):
        processed_condition = self._substitute_context_vars_sparql(str(condition_str))
        sparql_ask = f"ASK {{ {processed_condition} }}"
        return self.graph.query(sparql_ask, initNs=self.INIT_NS).askAnswer
    
    def execute_action(self, action_str):
        action_str_val = str(action_str)
        if action_str_val.startswith("SPARQL:"):
            sparql_update = action_str_val[7:].strip()
            processed_update = self._substitute_context_vars_sparql(sparql_update)
            self.graph.update(processed_update, initNs=self.INIT_NS)
        else: self._execute_custom_action(action_str_val)
    
    def _execute_custom_action(self, action): print(f"Executing custom action: {action}")

class TemplateExecutor:
    def __init__(self, graph, context_manager, rule_processor, ont_ns, init_ns_map): 
        self.graph = graph
        self.context_manager = context_manager
        self.rule_processor = rule_processor
        self.ONT_NS = ont_ns # Keep ONT_NS if used for direct URI construction
        self.INIT_NS = init_ns_map 

    def _execute_rule_application(self, operation_uri):
        rule_type_uri = self.graph.value(operation_uri, self.ONT_NS.ruleType)
        
        # Build query dynamically based on whether rule_type_uri is present
        # Ensure ont:priority is handled correctly if it's optional.
        # The OPTIONAL block and ORDER BY DESC(?prio) handles cases where priority might not be present.
        if rule_type_uri:
            rules_query = f"""
                SELECT ?rule ?condition ?action WHERE {{
                    ?rule a ont:Rule ; a <{rule_type_uri}> ; 
                          ont:condition ?condition ; ont:action ?action .
                    OPTIONAL {{ ?rule ont:priority ?prio . }}
                }} ORDER BY DESC(?prio)"""
        else: 
            rules_query = """
                SELECT ?rule ?condition ?action WHERE {
                    ?rule a ont:Rule ; ont:condition ?condition ; ont:action ?action .
                    OPTIONAL { ?rule ont:priority ?prio . }
                } ORDER BY DESC(?prio)"""
        
        rules_results = self.graph.query(rules_query, initNs=self.INIT_NS)
        for rule_row in rules_results:
            rule, condition, action = rule_row[0], rule_row[1], rule_row[2]
            if self.rule_processor.evaluate_condition(condition):
                self.rule_processor.execute_action(action)
        return None 

    def execute(self, template_uri):
        phases_query_result = self.graph.query(f"SELECT ?phase ?order WHERE {{ <{template_uri}> ont:hasPhase ?phase . ?phase ont:order ?order . }} ORDER BY ?order", initNs=self.INIT_NS)
        
        all_phase_results = {} 
        last_phase_result = None

        for phase_row in phases_query_result:
            phase, order = phase_row[0], phase_row[1]
            current_phase_result = self.execute_phase(phase)
            all_phase_results[str(phase)] = current_phase_result
            # The actual result of a template is typically the result of its last phase,
            # especially if it's a formatting phase that constructs the output string.
            last_phase_result = current_phase_result
        
        return last_phase_result


    def execute_phase(self, phase_uri):
        phase_type = self.graph.value(phase_uri, self.ONT_NS.phaseType)
        if not phase_type: raise ValueError(f"No phaseType defined for phase {phase_uri}")
        if phase_type == self.ONT_NS.AtomicOperationPhase: return self.execute_atomic_operation(phase_uri)
        elif phase_type == self.ONT_NS.SubTemplatePhase: return self.execute_subtemplate(phase_uri)
        elif phase_type == self.ONT_NS.ConditionalPhase: return self.execute_conditional_phase(phase_uri)
        else: raise ValueError(f"Unknown phase type: {phase_type} for phase {phase_uri}")
    
    def execute_atomic_operation(self, operation_uri):
        op_type = self.graph.value(operation_uri, self.ONT_NS.operationType)
        if not op_type: raise ValueError(f"No operationType defined for operation {operation_uri}")
        if op_type == self.ONT_NS.SPARQLQueryOperation: return self.execute_sparql_query(operation_uri)
        elif op_type == self.ONT_NS.SPARQLUpdateOperation: return self._execute_sparql_update(operation_uri)
        elif op_type == self.ONT_NS.RuleApplicationOperation: return self._execute_rule_application(operation_uri)
        elif op_type == self.ONT_NS.FormulaOperation: return self.execute_formula(operation_uri)
        elif op_type == self.ONT_NS.CustomFunctionOperation: return self.execute_custom_function(operation_uri)
        else: raise ValueError(f"Unknown operation type: {op_type} for operation {operation_uri}")
    
    def _substitute_context_vars_sparql(self, query_string): 
        variables = re.findall(r'\$context\.([a-zA-Z0-9_.]+)', query_string)
        processed_query = query_string
        for var_path in set(variables):
            try:
                value = self.context_manager.resolve_variable(var_path)
                if isinstance(value, str):
                    is_uri_like = value.startswith("http://") or value.startswith("<")
                    is_prefixed = False
                    if not is_uri_like and ':' in value:
                        prefix = value.split(':')[0]
                        if prefix in self.INIT_NS or prefix in [p for p,_ in self.graph.namespaces()]: # Check broader list
                           is_prefixed = True
                    if is_uri_like or is_prefixed:
                        processed_query = processed_query.replace(f"$context.{var_path}", value)
                    else: processed_query = processed_query.replace(f"$context.{var_path}", f'"{value}"')
                elif isinstance(value, URIRef): processed_query = processed_query.replace(f"$context.{var_path}", f"<{str(value)}>")
                elif isinstance(value, Literal): processed_query = processed_query.replace(f"$context.{var_path}", value.n3())
                else: processed_query = processed_query.replace(f"$context.{var_path}", str(value))
            except KeyError as e: print(f"Warning: Context variable $context.{var_path} not found for SPARQL substitution: {e}")
        return processed_query

    def execute_sparql_query(self, operation_uri):
        query_str = str(self.graph.value(operation_uri, self.ONT_NS.query))
        processed_query_str = self._substitute_context_vars_sparql(query_str)
        result = self.graph.query(processed_query_str, initNs=self.INIT_NS)
        # The CONSTRUCT queries in templates.ttl use a SELECT subquery with GROUP_CONCAT.
        # This means the result from rdflib will be a list of tuples, where each tuple has one Literal.
        # e.g., [(Literal('{"joints": [...]}'),)]
        return list(result) 


    def _execute_sparql_update(self, operation_uri):
        query_str = str(self.graph.value(operation_uri, self.ONT_NS.query))
        processed_query_str = self._substitute_context_vars_sparql(query_str)
        self.graph.update(processed_query_str, initNs=self.INIT_NS)
        return None # SPARQL Updates don't return values
    
    def execute_formula(self, operation_uri):
        formula_template = str(self.graph.value(operation_uri, self.ONT_NS.formula))
        processed_formula = formula_template
        var_paths = re.findall(r'\$context\.([a-zA-Z0-9_.]+)', processed_formula)
        for var_path in set(var_paths):
            try:
                value = self.context_manager.resolve_variable(var_path)
                processed_formula = processed_formula.replace(f"$context.{var_path}", repr(value))
            except KeyError as e: print(f"Warning: Context variable $context.{var_path} for formula not found: {e}")
        try:
            allowed_globals = {"math": math, "__builtins__": {"abs": abs, "min": min, "max": max, "round": round, "ceil": math.ceil, "floor": math.floor}}
            result = eval(processed_formula, allowed_globals, {})
            stores_result_as = self.graph.value(operation_uri, self.ONT_NS.storesResultAs)
            if stores_result_as: self.context_manager.update_context({str(stores_result_as).strip(): result})
            return result
        except Exception as e: raise ValueError(f"Formula evaluation failed for: '{processed_formula}'. Original: '{formula_template}'. Error: {str(e)}")
    
    def execute_custom_function(self, operation_uri):
        func_name = self.graph.value(operation_uri, self.ONT_NS.functionName)
        return f"Result of {func_name}" # Placeholder
    
    def execute_subtemplate(self, phase_uri):
        subtemplate_uri = self.graph.value(phase_uri, self.ONT_NS.callsTemplate)
        if not subtemplate_uri: raise ValueError(f"No callsTemplate defined for subtemplate phase {phase_uri}")
        return self.execute(subtemplate_uri) # Call main execute method for the subtemplate
    
    def execute_conditional_phase(self, phase_uri):
        condition_str = str(self.graph.value(phase_uri, self.ONT_NS.condition))
        # Assuming condition is a SPARQL ASK query body that might contain $context vars
        processed_condition_body = self._substitute_context_vars_sparql(condition_str) 
        ask_query = f"ASK {{ {processed_condition_body} }}" 
        
        if self.graph.query(ask_query, initNs=self.INIT_NS).askAnswer:
            true_phase = self.graph.value(phase_uri, self.ONT_NS.truePhase)
            if true_phase: return self.execute_phase(true_phase)
        else:
            false_phase = self.graph.value(phase_uri, self.ONT_NS.falsePhase)
            if false_phase: return self.execute_phase(false_phase)
        return None
