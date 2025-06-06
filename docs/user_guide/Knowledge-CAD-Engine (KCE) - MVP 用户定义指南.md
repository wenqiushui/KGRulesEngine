
# Knowledge-CAD-Engine (KCE) - MVP 用户定义指南

**文档版本:** 0.1
**日期:** 2025-06-07
**面向用户:** 领域专家 (Definition Author)

**1. 引言**

欢迎使用Knowledge-CAD-Engine (KCE)！本指南将引导您如何定义KCE的核心构建块：**本体 (Ontology)**、**能力模板 (Capability Templates)**、**原子节点 (Atomic Nodes)** 和 **规则 (Rules)**。通过正确定义这些元素，您可以将您的领域知识赋能给KCE，使其能够自动化解决您领域内的复杂问题。

KCE MVP版本主要通过YAML文件来接收这些定义。KCE内部会将这些YAML定义转换为RDF格式，并存储在其知识库中。

**2. 准备工作：理解KCE核心概念**

在开始定义之前，请确保您已理解以下KCE核心概念：

*   **知识图谱 (Knowledge Graph):** KCE的核心数据结构，使用RDF（资源描述框架）存储所有信息，包括您的定义、问题实例数据以及KCE的执行过程和结果。
*   **本体 (Ontology):** 描述您领域中概念、属性和它们之间关系的“词典”和“规则书”。KCE有一个核心本体来定义其自身框架的元素，您通常需要定义一个领域本体来描述您特定问题的实体。
*   **原子节点 (Atomic Node):** 代表一个具体的操作或计算步骤。它有明确的输入前提 (Preconditions)、输入参数 (InputParameters)、预期效果 (Effects) 和输出参数 (OutputParameters)，以及一个具体的实现（MVP中主要是Python脚本）。
*   **能力模板 (Capability Template):** 一个可复用的能力描述，定义了某种抽象功能需要什么类型的输入和会产生什么类型的输出。节点可以声明它实现了某些能力模板。
*   **规则 (Rule):** 定义了“如果...那么...”的逻辑。它包含一个条件部分 (Antecedent) 和一个结论/动作部分 (Consequent)。规则用于数据派生、状态转换或影响KCE的规划决策。
*   **动态规划 (Dynamic Planning):** KCE的核心机制。您定义好节点和规则后，只需告诉KCE您的问题（初始状态）和目标，KCE的规划器会自动找出一条或多条可行的路径（节点执行和规则应用的序列）来达成目标。
*   **执行状态图 (Execution State Graph):** KCE会记录其规划和执行的每一步，形成一个可追溯的状态图，便于调试和理解。

**3. 定义文件结构与通用约定**

*   **文件格式:** 所有KCE定义文件均使用YAML格式。
*   **文件组织:** 建议将不同类型的定义存放在不同的子目录中，例如：
    *   `ontologies/` (存放 `.ttl` 或 `.owl` 本体文件)
    *   `configurations/nodes/`
    *   `configurations/rules/`
    *   `configurations/capabilities/`
*   **ID与URI:** 每个核心定义（节点、规则、能力模板）都必须有一个全局唯一的ID。在YAML中，这通常是一个字符串。KCE内部会将其转换为一个URI。建议使用类似CURIE的格式（例如 `kce_nodes:MyNode`, `my_domain_rules:SomeRule`），并在KCE配置中定义前缀。
*   **注释:** YAML文件支持使用 `#` 进行注释，请善用注释来解释您的定义。
*   **引用其他定义:** 可以通过ID/URI引用其他已定义的KCE元素。

**4. 定义本体 (Ontologies)**

KCE依赖本体来理解您领域中的数据。

*   **KCE核心本体:** `kce_core_ontology.ttl` (由KCE框架提供)，定义了如 `kce:Node`, `kce:Rule` 等框架概念。您在定义节点和规则时会用到这些概念。
*   **领域本体:** 您需要为您特定的应用领域创建一个或多个本体文件 (推荐使用Turtle `.ttl` 或 RDF/XML `.owl` 格式)。
    *   **内容:** 定义您领域中的类 (Classes)、数据属性 (Data Properties)、对象属性 (Object Properties) 及其层级关系、域 (domain)、范围 (range) 等。
    *   **示例 (elevator_design.ttl - 简化):**
        ```turtle
        @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
        @prefix kce_domain: <http://example.org/kce_elevator_domain#> .

        kce_domain:ElevatorCar rdf:type owl:Class ;
            rdfs:label "Elevator Car" .

        kce_domain:carWidth rdf:type owl:DatatypeProperty ;
            rdfs:label "Car Width" ;
            rdfs:domain kce_domain:ElevatorCar ;
            rdfs:range xsd:integer .

        kce_domain:Panel rdf:type owl:Class ;
            rdfs:label "Panel" .
        # ... 更多定义 ...
        ```
*   **加载:** 使用 `kce load-defs` 命令时，指定本体文件所在的路径。

**5. 定义能力模板 (Capability Templates)**

能力模板描述了一种抽象的功能签名，用于促进节点能力的声明和发现。

*   **文件示例 (`configurations/capabilities/stiffener_calculation_capability.yaml`):**
    ```yaml
    id: kce_caps:StiffenerCalculation # 全局唯一ID
    type: kce:CapabilityTemplate     # 表明这是一个能力模板定义
    label: "Capability to calculate stiffener requirements"
    description: "Defines the abstract interface for calculating the number of stiffeners based on panel width."

    # 能力的输入接口描述
    inputInterface:
      - name: "panelWidth"            # 抽象输入参数名
        type: "xsd:integer"          # 期望的数据类型 (XSD类型)
        description: "The width of the panel in mm."
        # required: true (可选, 默认为true)

    # 能力的输出接口描述
    outputInterface:
      - name: "stiffenerCount"        # 抽象输出参数名
        type: "xsd:integer"          # 产生的数据类型
        description: "Number of stiffeners required for the panel."
    ```
*   **字段说明:**
    *   `id`: 必填，全局唯一ID。
    *   `type`: 必填，固定为 `kce:CapabilityTemplate`。
    *   `label`: 可选，人类可读的名称。
    *   `description`: 可选，详细描述。
    *   `inputInterface`: 一个列表，描述此能力期望的输入。
        *   `name`: 抽象参数名。
        *   `type`: 期望的数据类型（XSD标准类型，或您在本体中定义的类URI）。
        *   `description`: 参数描述。
        *   `required`: (可选，默认true) 此输入是否为必需。
    *   `outputInterface`: 一个列表，描述此能力产生的输出。结构同`inputInterface`。

**6. 定义原子节点 (Atomic Nodes)**

原子节点是KCE执行的具体操作单元。

*   **文件示例 (`configurations/nodes/calculate_stiffeners_node.yaml`):**
    ```yaml
    id: kce_nodes:CalculateStiffeners # 全局唯一ID
    type: kce:AtomicNode           # 表明这是一个原子节点定义
    label: "Calculate Panel Stiffeners"
    description: "Calculates the number of stiffeners required for a panel based on its width."

    # (可选) 声明此节点实现了哪些能力模板及其映射
    implementsCapability:
      - capabilityURI: kce_caps:StiffenerCalculation # 指向能力模板的ID
        # 将能力模板的抽象输入映射到此节点的具体输入参数名
        inputMappings:
          panelWidth: "nodeInput_PanelWidth"
        # 将能力模板的抽象输出映射到此节点的具体输出参数名
        outputMappings:
          stiffenerCount: "nodeOutput_StiffenerCount"

    # 节点执行的前提条件
    preconditions:
      # 可以是SPARQL ASK查询字符串，或引用本体中定义的约束
      # ?thisNodeInstance 是一个占位符，代表当前要执行的这个节点将作用的上下文或主要实体
      # 例如，假设此节点作用于一个 Panel 实例，该实例在规划时已确定
      - type: "SPARQL_ASK"
        query: |
          PREFIX kce_domain: <http://example.org/kce_elevator_domain#>
          ASK {
            ?panel rdf:type kce_domain:Panel . # 确保有一个Panel上下文
            ?panel kce_domain:panelWidth ?width . # 确保Panel的宽度已知
            # BIND(IRI(STR(?thisNodeContext)) AS ?panel) # 一种可能的上下文绑定方式
          }
        description: "Panel must exist and have a defined width."

    # 节点的输入参数定义
    inputParameters:
      - name: "nodeInput_PanelWidth"   # 节点内部使用的参数名 (需与implementsCapability中映射对应)
        rdfProperty: "kce_domain:panelWidth" # 从知识图谱中哪个RDF属性获取此输入值
                                          # (相对于当前操作的上下文实体, e.g., a specific Panel URI)
        dataType: "xsd:integer"
        description: "Width of the panel to calculate stiffeners for."
        # required: true (可选, 默认为true)

    # 节点执行后对知识图谱产生的预期效果/变更
    effects:
      # 描述节点执行成功后会发生什么，例如哪些RDF属性会被创建/更新
      # 可以是SPARQL UPDATE模板的元描述，或更抽象的声明
      - type: "RDF_PROPERTY_ASSERTION"
        description: "Asserts the kce_domain:stiffenerCount property on the panel."
        onEntity: "?panel" # 作用于哪个实体 (与precondition中的实体对应)
        property: "kce_domain:stiffenerCount"
        valueFromOutput: "nodeOutput_StiffenerCount" # 值来源于哪个输出参数

    # 节点的输出参数定义
    outputParameters:
      - name: "nodeOutput_StiffenerCount" # 节点内部产生的输出名 (需与implementsCapability中映射对应)
        rdfProperty: "kce_domain:stiffenerCount" # (可选) 如果输出直接更新某个属性，可指明
        dataType: "xsd:integer"
        description: "The calculated number of stiffeners."

    # 节点的具体实现方式 (MVP主要支持Python脚本)
    implementation:
      type: "PythonScript"
      scriptPath: "scripts/calculate_stiffeners.py" # 相对于KCE项目根目录或指定脚本目录的路径
      # 参数如何传递给脚本 (示例: 命令行)
      argumentPassing:
        style: "CommandLineNamed" # "CommandLinePositional", "EnvironmentVariables", "JSONtoStdIn"
        arguments:
          - name: "--panel-width" # 脚本期望的命令行参数名
            valueFromInput: "nodeInput_PanelWidth" # 从节点的哪个输入参数获取值
      # 如何从脚本获取输出 (示例: 标准输出解析)
      outputParsing:
        style: "JSONfromStdOut" # "SingleValueFromStdOut", "RegexFromStdOut"
        outputs:
          - scriptOutputName: "stiffener_count" # 脚本输出JSON中的键名 (如果适用)
            mapsToNodeOutput: "nodeOutput_StiffenerCount" # 映射到节点的哪个输出参数
      # (可选) 声明此节点执行是否有外部副作用 (非RDF图谱修改)
      # hasExternalSideEffect: true
    ```
*   **字段说明:**
    *   `id`, `type` (固定为`kce:AtomicNode`), `label`, `description`: 同能力模板。
    *   `implementsCapability`: (可选) 列表，声明此节点实现了哪些能力。
        *   `capabilityURI`: 能力模板的ID。
        *   `inputMappings`, `outputMappings`: 将能力接口的抽象参数名映射到此节点的具体输入/输出参数名。
    *   `preconditions`: 列表，定义节点执行前知识图谱必须满足的条件。
        *   `type`: "SPARQL_ASK" (表示`query`字段是一个SPARQL ASK查询) 或其他未来可能支持的类型 (如"OWL_CONSTRAINT_CHECK")。
        *   `query`: (如果type是SPARQL_ASK) SPARQL ASK查询字符串。查询应返回`true`节点才能执行。可以使用占位符如`?thisNodeContext`来引用当前节点操作的主要目标实体URI（由规划器在规划时确定和绑定）。
        *   `description`: 条件描述。
    *   `inputParameters`: 列表，定义节点需要的输入。
        *   `name`: 节点内部使用的参数名。
        *   `rdfProperty`: 从知识图谱中哪个RDF属性获取此输入值（相对于`?thisNodeContext`）。
        *   `dataType`: 预期的数据类型。
        *   `description`: 参数描述。
        *   `required`: (可选，默认true)。
    *   `effects`: 列表，声明性地描述节点成功执行后对知识图谱的预期修改。
        *   `type`: "RDF_PROPERTY_ASSERTION" (表示会断言一个RDF属性), "ENTITY_CREATION" (会创建一个新实体) 等。
        *   `description`: 效果描述。
        *   `onEntity`: (如果适用) 效果作用于哪个实体 (通常是`?thisNodeContext`或由节点新创建的实体)。
        *   `property`: (如果适用) 被断言/修改的RDF属性URI。
        *   `valueFromOutput`: (如果适用) 属性值来源于节点的哪个输出参数。
    *   `outputParameters`: 列表，定义节点产生的输出。结构类似`inputParameters`。
    *   `implementation`: 定义节点的具体执行方式。
        *   `type`: "PythonScript" (MVP主要支持)。
        *   `scriptPath`: Python脚本的路径。
        *   `argumentPassing`: 定义如何将KCE的输入参数传递给脚本。
            *   `style`: "CommandLineNamed" (如`--name value`), "CommandLinePositional" (按顺序), "EnvironmentVariables", "JSONtoStdIn"。
            *   `arguments`: 列表，定义每个脚本参数的映射。
                *   `name`: 脚本期望的参数名 (如`--panel-width`)。
                *   `valueFromInput`: 对应节点的哪个`inputParameters.name`。
        *   `outputParsing`: 定义如何从脚本的执行结果中提取KCE的输出参数。
            *   `style`: "JSONfromStdOut" (脚本打印JSON到标准输出), "SingleValueFromStdOut", "RegexFromStdOut" (从标准输出用正则提取)。
            *   `outputs`: 列表，定义每个脚本输出的映射。
                *   `scriptOutputName`: 脚本输出中的标识 (如JSON键名)。
                *   `mapsToNodeOutput`: 对应节点的哪个`outputParameters.name`。
        *   `hasExternalSideEffect`: (可选，默认false)布尔值，标记此节点执行是否会产生KCE知识图谱之外的、不可轻易回滚的副作用（例如，调用外部CAD软件保存文件，发送邮件等）。规划器可能会对这类节点有特殊处理。

**7. 定义规则 (Rules)**

规则用于在KCE中表达逻辑推断、状态转换或决策。

*   **文件示例 (`configurations/rules/check_panel_width_rule.yaml`):**
    ```yaml
    id: kce_rules:CheckPanelWidthConstraint
    type: kce:Rule
    label: "Check Panel Width Constraint Rule"
    description: "If a calculated panel width exceeds its maximum allowable width, assert a constraint violation and suggest a replan goal."
    priority: 10 # (可选) 规则优先级，数字越大优先级越高

    # 规则的条件部分 (Antecedent)
    antecedent:
      # 基于SPARQL WHERE子句来匹配模式
      # ?panel 是在WHERE子句中绑定的变量
      type: "SPARQL_PATTERN"
      pattern: |
        PREFIX kce_domain: <http://example.org/kce_elevator_domain#>
        PREFIX kce: <http://example.org/kce_core_ontology#>
        ?panel rdf:type kce_domain:Panel ;
               kce_domain:panelWidth ?calculatedWidth ;
               kce_domain:maxAllowableWidth ?maxWidth .
        FILTER(?calculatedWidth > ?maxWidth)
        # (可选) 确保此问题尚未被标记或处理
        FILTER NOT EXISTS { ?panel kce:hasActiveConstraintViolation ?violation . }

    # 规则的结论/动作部分 (Consequent)
    # 通过SPARQL INSERT/UPDATE模板来修改知识图谱
    # 可以使用在Antecedent中绑定的变量 (如 ?panel, ?calculatedWidth)
    consequent:
      - type: "SPARQL_UPDATE"
        update: |
          PREFIX kce_domain: <http://example.org/kce_elevator_domain#>
          PREFIX kce: <http://example.org/kce_core_ontology#>
          PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
          INSERT {
            ?panel kce:hasActiveConstraintViolation [
              rdf:type kce:ConstraintViolation ;
              kce:violationDetails (concat("Panel width ", STR(?calculatedWidth), " exceeds max ", STR(?maxWidth)))
            ] .
            # 也可以在这里创建一个新的目标实体来触发特定解决方案
            # _:newGoal rdf:type kce:Goal ;
            #           kce:goalDescription (concat("Resolve width violation for panel ", STR(?panel))) ;
            #           kce:relatedEntity ?panel ;
            #           kce:status "Pending" .
          }
          DATA {} # INSERT DATA {} 形式，或者 INSERT { ... } WHERE {} 形式 （如果需要从WHERE中获取更多变量）
                  # 对于简单的INSERT， DATA {} 可能更直接。
                  # 如果Consequent需要基于Antecedent的匹配进行更复杂的插入，
                  # 那么Consequent的update也应该包含一个WHERE子句来重新绑定变量。
                  # 更安全的做法是，Consequent的SPARQL UPDATE也包含与Antecedent相同的匹配模式在WHERE子句中。
                  # 例如：
                  # INSERT { ?panel kce:hasActiveConstraintViolation ... }
                  # WHERE {
                  #   ?panel rdf:type kce_domain:Panel ;
                  #          kce_domain:panelWidth ?calculatedWidth ;
                  #          kce_domain:maxAllowableWidth ?maxWidth .
                  #   FILTER(?calculatedWidth > ?maxWidth)
                  #   FILTER NOT EXISTS { ?panel kce:hasActiveConstraintViolation ?violation . }
                  # }

      # Consequent也可以是其他类型，例如 "SET_GOAL" (创建一个新的规划目标)
      # - type: "SET_GOAL"
      #   goalDescriptionTemplate: "Resolve width violation for panel {panel_uri}"
      #   goalParameters:
      #     panel_uri: "?panel" # 从Antecedent绑定的变量
    ```
*   **字段说明:**
    *   `id`, `type` (固定为`kce:Rule`), `label`, `description`: 同上。
    *   `priority`: (可选) 整数，用于规则冲突解决，数字越大优先级越高。
    *   `antecedent`: 规则的条件部分。
        *   `type`: "SPARQL_PATTERN" (表示`pattern`字段是一个SPARQL `WHERE`子句的内容，不包含`WHERE`关键字本身)。
        *   `pattern`: SPARQL `WHERE`子句字符串。如果此模式在当前知识图谱中能找到匹配（即查询有结果），则条件满足。
    *   `consequent`: 规则的动作部分，是一个列表，可以包含多个动作。
        *   `type`: "SPARQL_UPDATE" (表示`update`字段是一个SPARQL UPDATE语句/模板) 或 "SPARQL_CONSTRUCT" (如果规则仅用于派生新数据而不直接修改现有数据)。未来可能支持 "SET_GOAL" 等专用类型。
        *   `update` / `construct`: SPARQL UPDATE 或 CONSTRUCT 语句字符串。可以使用在`antecedent.pattern`中绑定的变量。**重要:** 为确保操作的原子性和正确性，`SPARQL_UPDATE`的`WHERE`子句应尽可能重复`antecedent.pattern`中的匹配逻辑，以确保只在条件真正满足时进行修改。

**8. 定义问题 (Problem Instance)**

问题实例通常在运行时通过CLI参数（引用一个JSON文件）提供。

*   **文件示例 (`configurations/problems/car_design_case1.json`):**
    ```json
    {
      "comment": "Problem definition for a specific car design case",
      "initialState": [ // 描述初始状态的RDF三元组 (可以用簡化Turtle或JSON-LD表示)
        {
          "@id": "ex:MyCarInstance123", // 使用@id指定URI
          "@type": "kce_domain:ElevatorCar", // 使用@type指定rdf:type
          "kce_domain:carWidth": { "@value": "1500", "@type": "xsd:integer" },
          "kce_domain:carHeight": { "@value": "2450", "@type": "xsd:integer" }
        },
        {
          // 可以有多个初始实体
          "@id": "ex:MyRearWallAssembly456",
          "@type": "kce_domain:RearWallAssembly",
          "kce_domain:partOfCar": { "@id": "ex:MyCarInstance123" } // 对象属性用@id引用
        }
      ],
      "targetGoal": { // 描述求解的目标
        "type": "SPARQL_ASK", // 或 "RDF_PATTERN_MATCH"
        "query": """
          PREFIX kce_domain: <http://example.org/kce_elevator_domain#>
          PREFIX ex: <http://example.org/instances/>
          ASK {
            ex:MyRearWallAssembly456 kce_domain:totalAssemblyCost ?cost ;
                                     kce:hasAllJointsGenerated true .
                                     # kce:hasAllJointsGenerated 是一个需要KCE通过某种方式断言的状态
          }
        """
        // 或者使用RDF模式描述期望的最终状态：
        // "pattern": [
        //   { "@id": "ex:MyRearWallAssembly456", "kce_domain:totalAssemblyCost": "?any", "kce:hasAllJointsGenerated": true }
        // ]
      },
      "executionMode": "user" // "user" 或 "expert"
      // "runId": "optional_user_specified_run_id" // (可选)
    }
    ```
*   **字段说明:**
    *   `initialState`: 一个对象数组，每个对象代表一组要加载到知识图谱中的初始RDF三元组。这里使用了类似JSON-LD的表示法：
        *   `@id`: 实体的URI。
        *   `@type`: 实体的`rdf:type`。
        *   属性名 (如`kce_domain:carWidth`):
            *   对于数据属性，其值为一个对象 `{"@value": "value", "@type": "xsd:dataType"}`。
            *   对于对象属性，其值为一个对象 `{"@id": "uri_of_related_entity"}`。
        *   KCE的“定义与转换层”需要能解析这种结构并生成RDF。
    *   `targetGoal`: 描述求解的目标。
        *   `type`: "SPARQL_ASK" (表示`query`是一个SPARQL ASK查询，期望结果为true) 或 "RDF_PATTERN_MATCH" (表示`pattern`是一个RDF模式，期望知识图谱中存在匹配此模式的子图)。
        *   `query` / `pattern`: 具体内容。
    *   `executionMode`: (可选, 默认"user") "user" 或 "expert"。

**9. 编写Python脚本 (节点实现)**

*   当节点定义中的`implementation.type`为"PythonScript"时，您需要提供相应的Python脚本。
*   **参数传递:** 根据`argumentPassing.style`，脚本会以不同方式接收输入参数。
    *   例如，对于`CommandLineNamed`，脚本可以使用`argparse`库来解析命令行参数。
*   **输出:** 根据`outputParsing.style`，脚本需要以特定格式输出结果。
    *   例如，对于`JSONfromStdOut`，脚本需要将其计算结果组织成一个JSON对象，并打印到标准输出。
*   **示例 (`scripts/calculate_stiffeners.py` - 简化):**
    ```python
    import argparse
    import json

    def calculate_stiffeners(panel_width):
        if panel_width <= 300:
            return 0
        elif panel_width <= 500:
            return 1
        else:
            return 2

    if __name__ == "__main__":
        parser = argparse.ArgumentParser()
        parser.add_argument("--panel-width", type=int, required=True)
        args = parser.parse_args()

        count = calculate_stiffeners(args.panel_width)
        
        # Output as JSON to stdout
        output_data = {
            "stiffener_count": count
            # 如果有其他输出，也放在这里
        }
        print(json.dumps(output_data))
    ```

**10. 版本控制约定 (MVP简化)**

*   **文件名/目录:** 建议在您的定义文件名或目录结构中包含版本信息，例如：
    *   `configurations/v1.0/nodes/calculate_stiffeners_node.yaml`
    *   `ontologies/v1.1/elevator_design.ttl`
*   **KCE加载:** 当您使用`kce load-defs`时，加载特定版本目录下的所有定义。
*   **问题定义中引用:** (可选，更高级) 如果问题定义需要指定其依赖的节点/规则版本，可以在JSON中添加一个元数据字段，但MVP的KCE规划器可能不直接使用此信息强制版本匹配，而是依赖用户加载了正确的版本集。

**11. 总结与最佳实践**

*   **从小处着手:** 先定义核心的本体概念和几个关键的节点/规则。
*   **迭代完善:** KCE的定义是一个迭代的过程。先运行简单的场景，根据结果和日志逐步调试和完善您的定义。
*   **清晰命名:** 为您的ID、属性、参数使用清晰、一致且有意义的名称。
*   **善用注释:** 在YAML文件中添加注释来解释您的设计意图。
*   **模块化:** 将复杂问题分解为更小的、可管理的节点和规则。利用能力模板来复用功能描述。
*   **声明式思考:** 尽量用声明的方式描述节点的效果和规则的逻辑，而不是命令式的步骤。KCE的规划器会负责找出执行顺序。
*   **与KCE团队沟通:** 如果您在如何将领域知识映射到KCE概念时遇到困难，请及时与KCE的架构师或产品经理沟通。

本指南提供了KCE MVP版本定义语言的核心要素。随着KCE的发展，可能会引入更高级的定义特性和更友好的定义方式。祝您使用KCE愉快！