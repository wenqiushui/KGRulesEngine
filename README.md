# KGRulesEngine：基于知识图谱的通用规则引擎

## 项目概述

KGRulesEngine 是一个基于知识图谱的通用规则引擎，它通过 RDF/OWL 语义模型和声明式规则配置，实现了"配置即开发"的业务逻辑处理范式。该引擎特别适用于需要复杂规则推理和动态决策的领域，如机械设计、制造流程优化、产品配置等领域。

## 核心特性

- **声明式规则配置**：使用 RDF/Turtle 语法定义业务规则，无需编写代码
- **动态模板执行**：支持复杂业务流程的模板化定义和执行
- **本体推理能力**：集成 OWL-RL 推理机实现语义推理
- **多领域支持**：通用架构适用于各种业务场景
- **实时变更响应**：规则和模板变更即时生效
- **图模式匹配**：强大的图模式匹配能力处理复杂关系

## 安装与使用

### 系统要求
- Python 3.8+
- 支持 SPARQL 1.1 的 RDF 库

### 安装步骤

```bash
# 克隆仓库
git clone https://github.com/yourusername/kgrulesengine.git
cd kgrulesengine

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate    # Windows

# 安装依赖
pip install -r requirements.txt
```

### 快速开始

```python
from kgrulesengine import GraphPatternEngine

# 初始化引擎
engine = GraphPatternEngine()

# 加载知识库
engine.load_ontology("examples/wall_panel/ontology.ttl")
engine.load_rules("examples/wall_panel/rules.ttl")
engine.load_templates("examples/wall_panel/templates.ttl")

# 设置上下文并执行查询
context = {"cabinet_height": 2450, "cabinet_width": 1500}
result = engine.query("http://elevator.com/ontology#DimensionCalculation", context)

# 处理结果
dimensions = json.loads(f"[{result['_:result']['dimensions']}]")
print(json.dumps(dimensions, indent=2))
```

## 项目结构

```
kgrulesengine/
├── kgrulesengine/          # 引擎核心代码
│   ├── __init__.py
│   ├── engine.py           # 引擎主类
│   ├── context.py          # 上下文管理
│   ├── rule_processor.py   # 规则处理器
│   ├── template_executor.py # 模板执行器
│   └── utils.py            # 工具函数
├── examples/               # 示例项目
│   └── wall_panel/         # 轿厢壁板案例
│       ├── ontology.ttl    # 本体定义
│       ├── rules.ttl       # 业务规则
│       ├── templates.ttl   # 流程模板
│       └── test_cases.py   # 测试用例
├── tests/                  # 单元测试
│   └── test_engine.py
├── requirements.txt        # 依赖库
├── LICENSE                 # 开源协议
└── README.md               # 项目文档
```

## 依赖库

requirements.txt 内容：
```
rdflib==6.3.2
owlrl==6.0.2
SPARQLWrapper==2.0.0
pyparsing==3.1.1
requests==2.31.0
```

## 完整示例：轿厢壁板设计

### 1. 定义本体 (ontology.ttl)
```turtle
@prefix : <http://elevator.com/ontology#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

# 壁板类定义
:WallPanel a rdfs:Class ;
    rdfs:label "壁板" .

# 配合关系类
:Joint a rdfs:Class ;
    rdfs:label "配合关系" .

# 尺寸计算问题类型
:DimensionCalculation a rdfs:Class ;
    rdfs:label "尺寸计算" .
```

### 2. 定义规则 (rules.ttl)
```turtle
@prefix : <http://elevator.com/ontology#> .
@prefix rule: <http://example.com/rules#> .

# 厚度计算规则
rule:ThicknessRule a :Rule ;
    :condition "$context.cabinet_height <= 2300" ;
    :action """
        INSERT {
            ?panel :thickness 1.3 ;
                   :bendHeight 25 .
        }
        WHERE { ?panel a :WallPanel }
    """ .
```

### 3. 定义模板 (templates.ttl)
```turtle
@prefix : <http://elevator.com/ontology#> .
@prefix tmpl: <http://example.com/templates#> .

# 尺寸计算模板
tmpl:DimensionCalculationTemplate a :Template ;
    :problemType :DimensionCalculation ;
    :hasPhase tmpl:PanelSizeSetupPhase, tmpl:DimensionRulePhase .

tmpl:PanelSizeSetupPhase a :Phase ;
    :phaseType :AtomicOperationPhase ;
    :operationType :SPARQLQueryOperation ;
    :query """
        INSERT DATA {
            :LeftPanel :width ($context.cabinet_width - 700) / 2 ;
                      :height $context.cabinet_height .
            :MiddlePanel :width 700 ;
                      :height $context.cabinet_height .
            :RightPanel :width ($context.cabinet_width - 700) / 2 ;
                      :height $context.cabinet_height .
        }
    """ .
```

### 4. 测试用例 (test_cases.py)
```python
def test_dimension_calculation():
    engine = GraphPatternEngine()
    engine.load_ontology("ontology.ttl")
    engine.load_rules("rules.ttl")
    engine.load_templates("templates.ttl")
    
    context = {"cabinet_height": 2450, "cabinet_width": 1500}
    result = engine.query("http://elevator.com/ontology#DimensionCalculation", context)
    
    # 验证结果
    assert "LeftPanel" in result
    assert result["LeftPanel"]["width"] == 400
    assert result["LeftPanel"]["thickness"] == 1.5
```

## API 参考

### GraphPatternEngine 类

#### 方法：
- `load_ontology(ttl_file: str)`: 加载本体定义文件
- `load_rules(ttl_file: str)`: 加载业务规则文件
- `load_templates(ttl_file: str)`: 加载流程模板文件
- `set_context(context: dict)`: 设置当前上下文
- `query(problem_type: str, params: dict = None)`: 执行查询

### ContextManager 类
- `set_context(context: dict)`: 设置完整上下文
- `update_context(updates: dict)`: 更新部分上下文
- `resolve_variable(path: str)`: 解析变量路径

## 贡献指南

我们欢迎各种形式的贡献！请遵循以下步骤：

1. Fork 仓库
2. 创建新分支 (`git checkout -b feature/your-feature`)
3. 提交变更 (`git commit -am 'Add some feature'`)
4. 推送到分支 (`git push origin feature/your-feature`)
5. 创建 Pull Request

## 许可证

本项目采用 MIT 许可证 


## 路线图

- [ ] v0.1 基础引擎实现
- [ ] v0.2 性能优化与缓存机制
- [ ] v0.3 可视化规则编辑器
- [ ] v0.4 分布式推理支持
- [ ] v1.0 正式生产版本

## 致谢

本项目受到以下项目的启发：
- RDFLib
- OWL-RL
- Apache Jena
- Neo4j

感谢所有贡献者的努力！

---
**KGRulesEngine** - 让复杂业务规则变得简单可控
