from rdflib import Graph, URIRef, Literal, Namespace, RDF, RDFS
from owlrl import DeductiveClosure, OWLRL_Semantics
import re

class GraphPatternEngine:
    def __init__(self):
        # 初始化RDF图
        self.knowledge_graph = Graph()
        
        # 命名空间
        self.ONT_NS = Namespace("http://example.com/ontology#")
        self.RULE_NS = Namespace("http://example.com/rules#")
        self.TMPL_NS = Namespace("http://example.com/templates#")
        
        # 绑定命名空间
        self.knowledge_graph.bind("ont", self.ONT_NS)
        self.knowledge_graph.bind("rule", self.RULE_NS)
        self.knowledge_graph.bind("tmpl", self.TMPL_NS)
        
        # 上下文管理器
        self.context_manager = ContextManager()
        
        # 规则处理器
        self.rule_processor = RuleProcessor(self.knowledge_graph, self.context_manager)
        
        # 模板执行器
        self.template_executor = TemplateExecutor(self.knowledge_graph, self.context_manager)

    def load_ontology(self, ttl_file):
        """加载本体定义"""
        self.knowledge_graph.parse(ttl_file, format="turtle")
        # 执行本体推理
        DeductiveClosure(OWLRL_Semantics).expand(self.knowledge_graph)

    def load_rules(self, ttl_file):
        """加载业务规则"""
        self.knowledge_graph.parse(ttl_file, format="turtle")

    def load_templates(self, ttl_file):
        """加载流程模板"""
        self.knowledge_graph.parse(ttl_file, format="turtle")

    def set_context(self, context_dict):
        """设置当前上下文"""
        self.context_manager.set_context(context_dict)

    def apply_rules(self):
        """应用所有相关规则"""
        # 查找所有规则
        rules = self.knowledge_graph.query("""
            SELECT ?rule ?condition ?action
            WHERE {
                ?rule a ont:Rule ;
                      ont:condition ?condition ;
                      ont:action ?action .
            }
            ORDER BY DESC(ont:priority)
        """)
        
        # 应用规则
        for rule, condition, action in rules:
            if self.rule_processor.evaluate_condition(condition):
                self.rule_processor.execute_action(action)

    def match_template(self, problem_type):
        """匹配问题类型对应的模板"""
        # 将问题类型转换为URI
        problem_uri = URIRef(problem_type)
        
        # 查找匹配的模板
        query = f"""
            SELECT ?template
            WHERE {{
                ?template a ont:Template ;
                         ont:problemType <{problem_uri}> ;
                         ont:available true .
            }}
            ORDER BY DESC(ont:priority)
            LIMIT 1
        """
        result = list(self.knowledge_graph.query(query))
        return result[0][0] if result else None

    def execute_template(self, template_uri):
        """执行模板"""
        return self.template_executor.execute(template_uri)

    def query(self, problem_type, params=None):
        """执行完整查询流程"""
        # 设置参数上下文
        if params:
            self.context_manager.update_context(params)
        
        # 应用业务规则
        self.apply_rules()
        
        # 匹配模板
        template_uri = self.match_template(problem_type)
        if not template_uri:
            raise ValueError(f"No template found for problem type: {problem_type}")
        
        # 执行模板
        result = self.execute_template(template_uri)
        
        return result


class ContextManager:
    def __init__(self):
        self.context = {}
    
    def set_context(self, context_dict):
        """设置完整上下文"""
        self.context = context_dict.copy()
    
    def update_context(self, updates):
        """更新部分上下文"""
        self.context.update(updates)
    
    def resolve_variable(self, path):
        """解析变量路径（如"panel.height"）"""
        parts = path.split('.')
        current = self.context
        for part in parts:
            if part in current:
                current = current[part]
            else:
                raise KeyError(f"Context variable not found: {path}")
        return current


class RuleProcessor:
    def __init__(self, graph, context_manager):
        self.graph = graph
        self.context_manager = context_manager
    
    def evaluate_condition(self, condition):
        """评估规则条件"""
        # 提取条件中的变量（如$context.panel.height）
        variables = re.findall(r'\$([a-zA-Z0-9_.]+)', condition)
        
        # 替换变量为实际值
        for var in set(variables):
            value = self.context_manager.resolve_variable(var)
            # 根据值类型进行适当引用
            if isinstance(value, str):
                condition = condition.replace(f"${var}", f'"{value}"')
            else:
                condition = condition.replace(f"${var}", str(value))
        
        # 转换为SPARQL ASK查询
        sparql_ask = f"ASK {{ {condition} }}"
        
        # 执行查询
        return self.graph.query(sparql_ask).askAnswer
    
    def execute_action(self, action):
        """执行规则动作"""
        # 动作可以是SPARQL更新或自定义操作
        if action.startswith("SPARQL:"):
            # 执行SPARQL更新
            sparql_update = action[7:].strip()
            self.graph.update(sparql_update)
        else:
            # 执行自定义操作
            self._execute_custom_action(action)
    
    def _execute_custom_action(self, action):
        """执行自定义动作（示例）"""
        # 在实际应用中，这里可以扩展为执行各种自定义操作
        print(f"Executing custom action: {action}")


class TemplateExecutor:
    def __init__(self, graph, context_manager):
        self.graph = graph
        self.context_manager = context_manager
        self.ONT_NS = Namespace("http://example.com/ontology#")
    
    def execute(self, template_uri):
        """执行模板"""
        # 获取模板的所有阶段
        phases = self.graph.query(f"""
            SELECT ?phase ?order
            WHERE {{
                <{template_uri}> ont:hasPhase ?phase .
                ?phase ont:order ?order .
            }}
            ORDER BY ?order
        """)
        
        # 按顺序执行每个阶段
        results = {}
        for phase, order in phases:
            phase_result = self.execute_phase(phase)
            results[str(phase)] = phase_result
        
        return results
    
    def execute_phase(self, phase_uri):
        """执行单个阶段"""
        # 获取阶段类型
        phase_type = self.graph.value(phase_uri, self.ONT_NS.phaseType)
        
        if phase_type == self.ONT_NS.AtomicOperationPhase:
            return self.execute_atomic_operation(phase_uri)
        elif phase_type == self.ONT_NS.SubTemplatePhase:
            return self.execute_subtemplate(phase_uri)
        elif phase_type == self.ONT_NS.ConditionalPhase:
            return self.execute_conditional_phase(phase_uri)
        else:
            raise ValueError(f"Unknown phase type: {phase_type}")
    
    def execute_atomic_operation(self, operation_uri):
        """执行原子操作"""
        # 获取操作类型
        op_type = self.graph.value(operation_uri, self.ONT_NS.operationType)
        
        if op_type == self.ONT_NS.SPARQLQueryOperation:
            return self.execute_sparql_query(operation_uri)
        elif op_type == self.ONT_NS.FormulaOperation:
            return self.execute_formula(operation_uri)
        elif op_type == self.ONT_NS.CustomFunctionOperation:
            return self.execute_custom_function(operation_uri)
        else:
            raise ValueError(f"Unknown operation type: {op_type}")
    
    def execute_sparql_query(self, operation_uri):
        """执行SPARQL查询操作"""
        query = self.graph.value(operation_uri, self.ONT_NS.query)
        return list(self.graph.query(query))
    
    def execute_formula(self, operation_uri):
        """执行公式计算"""
        formula = self.graph.value(operation_uri, self.ONT_NS.formula)
        
        # 提取公式中的变量
        variables = re.findall(r'\$([a-zA-Z0-9_.]+)', formula)
        
        # 替换变量为实际值
        for var in set(variables):
            value = self.context_manager.resolve_variable(var)
            formula = formula.replace(f"${var}", str(value))
        
        # 安全地执行公式计算
        try:
            return eval(formula, {"__builtins__": None}, {})
        except Exception as e:
            raise ValueError(f"Formula evaluation failed: {formula} - {str(e)}")
    
    def execute_custom_function(self, operation_uri):
        """执行自定义函数"""
        # 在实际应用中，这里可以扩展为执行各种自定义函数
        func_name = self.graph.value(operation_uri, self.ONT_NS.functionName)
        return f"Result of {func_name}"
    
    def execute_subtemplate(self, phase_uri):
        """执行子模板"""
        subtemplate = self.graph.value(phase_uri, self.ONT_NS.callsTemplate)
        return self.execute(subtemplate)
    
    def execute_conditional_phase(self, phase_uri):
        """执行条件阶段"""
        # 获取条件
        condition = self.graph.value(phase_uri, self.ONT_NS.condition)
        
        # 评估条件
        if self.rule_processor.evaluate_condition(condition):
            # 条件为真时执行的内容
            true_phase = self.graph.value(phase_uri, self.ONT_NS.truePhase)
            return self.execute_phase(true_phase)
        else:
            # 条件为假时执行的内容
            false_phase = self.graph.value(phase_uri, self.ONT_NS.falsePhase)
            if false_phase:
                return self.execute_phase(false_phase)
        return None
