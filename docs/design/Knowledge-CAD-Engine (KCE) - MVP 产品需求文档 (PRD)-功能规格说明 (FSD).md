**Knowledge-CAD-Engine (KCE) - MVP 产品需求文档 (PRD) / 功能规格说明 (FSD)**

**文档版本:** 0.1
**日期:** 2025-06-07
**状态:** 初稿

**1. 引言**

*   **1.1 项目目标与愿景**
    Knowledge-CAD-Engine (KCE) 旨在成为一个通用的、知识驱动的自动化引擎，能够帮助领域专家将其专业知识（如设计规则、计算方法、操作流程）形式化，并让领域用户能够基于这些知识自动解决特定问题（如参数化设计、成本估算、合规性检查）。KCE的核心优势在于其动态规划能力，即根据给定的初始状态、目标以及定义好的节点（操作）和规则（逻辑），自主推导出并执行解决方案。
*   **1.2 MVP目标**
    此MVP版本旨在验证KCE核心架构的可行性，包括：知识的RDF表示、基于YAML/JSON的节点与规则定义、动态流程规划与执行、外部脚本的节点化调用、以及独特的执行状态图管理机制。MVP将专注于解决一个简化的参数化设计与分析问题，以展示其核心能力。性能和图形化用户界面非MVP阶段的重点。
*   **1.3 目标用户**
    *   **领域专家 (Definition Author):** 负责将领域知识（计算逻辑、决策规则、操作步骤）转换为KCE可识别的节点和规则定义。他们需要理解KCE的定义规范。
    *   **领域用户 (Problem Solver):** 在已有的领域知识库（节点库、规则库）基础上，提交具体问题参数和求解目标，获取自动化解决方案。
*   **1.4 文档范围**
    本文档描述KCE MVP版本的功能需求、非功能性需求、核心工作流程以及验收标准。

**2. 核心功能需求**

*   **2.1 知识表示与管理**
    *   **FR-KM-001: RDF作为核心知识表示**
        *   **描述:** KCE应使用RDF三元组作为其内部知识表示的基础。所有本体、节点定义、规则定义、问题实例数据、执行日志和状态图都应能存储和查询为RDF。
        *   **验收标准:**
            *   AC1: 系统能加载符合RDF标准的本体文件 (TTL/OWL格式)。
            *   AC2: 系统能通过SPARQL 1.1查询语言对存储的RDF数据进行查询。
            *   AC3: 系统能通过SPARQL 1.1 UPDATE语言对存储的RDF数据进行修改。
    *   **FR-KM-002: KCE核心本体支持**
        *   **描述:** KCE应提供一个核心本体 (OWL/RDFS)，用于定义框架自身的概念，如节点、规则、参数、执行状态、能力模板等。
        *   **验收标准:**
            *   AC1: KCE核心本体文件 (`kce_core_ontology.ttl`) 包含对 `kce:Node`, `kce:AtomicNode`, `kce:InputParameter`, `kce:OutputParameter`, `kce:Precondition`, `kce:Effect`, `kce:Rule`, `kce:Antecedent`, `kce:Consequent`, `kce:ExecutionStateNode`, `kce:CapabilityTemplate` 等核心概念的定义。
    *   **FR-KM-003: OWL RL推理支持 (MVP简化)**
        *   **描述:** KCE应集成OWL RL推理能力，以基于定义的本体派生隐含知识。
        *   **验收标准:**
            *   AC1: 系统能在数据加载或特定命令触发后执行OWL RL推理。
            *   AC2: 推理出的三元组能被SPARQL查询到，并可用于后续的规划和执行决策。
    *   **FR-KM-004: 基于SQLite的RDF持久化存储**
        *   **描述:** MVP阶段，KCE应使用SQLite作为`rdflib`的后端，实现RDF数据的持久化存储。
        *   **验收标准:**
            *   AC1: KCE启动时能连接或创建指定的SQLite数据库文件。
            *   AC2: KCE运行中产生的数据（定义、实例、日志）能持久化到SQLite数据库中，并在下次启动时可加载。

*   **2.2 定义与转换 (YAML/JSON 到 RDF)**
    *   **FR-DEF-001: 原子节点定义 (YAML)**
        *   **描述:** 领域专家应能通过YAML格式文件定义原子节点及其元数据。
        *   **验收标准:**
            *   AC1: YAML文件能定义节点的URI、名称、描述。
            *   AC2: YAML文件能定义节点的`kce:Precondition` (SPARQL ASK查询或指向本体约束的引用)。
            *   AC3: YAML文件能定义节点的`kce:InputParameter` (名称、映射到RDF属性、数据类型)。
            *   AC4: YAML文件能定义节点的`kce:Effect` (描述节点执行后产生的RDF变更，可以是SPARQL UPDATE模板的元描述或新实体/属性的声明)。
            *   AC5: YAML文件能定义节点的`kce:OutputParameter` (名称、映射到RDF属性、数据类型)。
            *   AC6: YAML文件能定义节点的实现方式，MVP阶段至少支持“Python脚本调用”（包含脚本路径、参数传递方式）。
            *   AC7: (关联FR-CAP-001) YAML文件能声明节点实现的`kce:CapabilityTemplate`并提供映射。
    *   **FR-DEF-002: 规则定义 (YAML)**
        *   **描述:** 领域专家应能通过YAML格式文件定义声明式规则。
        *   **验收标准:**
            *   AC1: YAML文件能定义规则的URI、名称、描述、优先级。
            *   AC2: YAML文件能定义规则的`kce:Antecedent` (条件，SPARQL `WHERE`子句或结构化条件)。
            *   AC3: YAML文件能定义规则的`kce:Consequent` (结论/动作，SPARQL `CONSTRUCT`/`INSERT`/`UPDATE`模板，或用于设定新目标的RDF模式)。
    *   **FR-DEF-003: 能力模板定义 (YAML)**
        *   **描述:** 领域专家应能通过YAML格式文件定义可复用的能力模板。
        *   **验收标准:**
            *   AC1: YAML文件能定义能力模板的URI、名称、描述。
            *   AC2: YAML文件能定义能力模板的抽象`kce:InputInterface` (参数名、类型、描述)。
            *   AC3: YAML文件能定义能力模板的抽象`kce:OutputInterface` (参数名、类型、描述)。
    *   **FR-DEF-004: YAML/JSON到RDF的转换与加载**
        *   **描述:** KCE应能解析上述YAML定义文件，并将其转换为符合KCE核心本体的RDF三元组，加载到知识库中。
        *   **验收标准:**
            *   AC1: KCE提供CLI命令 (`kce load-defs <path_to_yaml_dir_or_file>`) 加载定义。
            *   AC2: 加载成功后，可以通过SPARQL查询到对应的节点、规则、能力模板的RDF表示。
            *   AC3: 对格式错误的YAML文件，系统应给出明确的错误提示。

*   **2.3 动态流程规划与执行**
    *   **FR-PLAN-001: 基于目标的动态流程规划**
        *   **描述:** KCE的规划器应能根据用户提供的初始状态和目标描述，结合知识库中已定义的节点和规则，动态推导出一个可执行的计划（节点执行和规则应用的序列）。
        *   **验收标准:**
            *   AC1: 用户能通过CLI提交问题，包含初始状态（例如，一个JSON文件，其内容将被转换为RDF并加载）和目标描述（例如，一个SPARQL ASK查询，或期望生成的某个RDF实体及其属性模式）。
            *   AC2: 规划器能从目标出发，反向或正向搜索可用的节点（其`Effect`有助于达成目标）和规则（其`Consequent`有助于达成目标或满足节点前提）。
            *   AC3: 规划器能递归地将节点的`Precondition`或规则的`Antecedent`设为子目标进行规划。
            *   AC4: MVP阶段的规划器能找到一个可行的（不一定最优）计划来达成目标。
            *   AC5: 如果无法找到计划，系统应明确报告规划失败及可能的原因。
    *   **FR-PLAN-002: 持续规划与适应性 (支持“检查-调整”模式)**
        *   **描述:** 规划器应能在节点执行或规则应用导致知识图谱状态变化后，根据最新状态继续规划后续步骤。这支持了“检查节点”通过修改知识图谱来影响后续流程的模式。
        *   **验收标准:**
            *   AC1: 当一个“检查节点”执行后，其`Effect`（例如，向知识图谱添加了`kce:ConstraintViolation`或新的`kce:Goal`）能被规划器在后续决策中感知。
            *   AC2: 规划器能根据这些新信息调整其路径选择，例如选择能够处理该约束冲突或新目标的节点/规则。
            *   AC3: 系统能避免简单的规划循环（例如，通过规划深度限制或状态访问历史）。
    *   **FR-EXEC-001: 计划执行器**
        *   **描述:** KCE应有一个计划执行器，负责按规划器生成的计划顺序执行操作。
        *   **验收标准:**
            *   AC1: 计划执行器能正确调用节点执行器来执行原子节点。
            *   AC2: 计划执行器能正确调用规则引擎来应用规则（执行其`Consequent`）。
            *   AC3: 节点执行或规则应用的输出（对知识图谱的修改）对后续步骤可见。
    *   **FR-EXEC-002: 原子节点执行 (Python脚本)**
        *   **描述:** KCE的节点执行器应能调用外部Python脚本作为原子节点的实现。
        *   **验收标准:**
            *   AC1: 节点执行器能根据节点定义中的实现规范，找到并执行指定的Python脚本。
            *   AC2: 能将节点定义中声明的输入参数（其值从知识图谱中获取）正确传递给Python脚本（例如，通过命令行参数）。
            *   AC3: 能捕获Python脚本的标准输出作为节点的输出结果。
            *   AC4: 能将脚本输出结果根据节点定义中的输出参数规范，写回知识图谱。
            *   AC5: 脚本执行失败（例如，非零退出码，抛出异常）应被捕获并记录为节点执行失败。
    *   **FR-RULE-001: 规则引擎 (基于SPARQL)**
        *   **描述:** KCE应有一个规则引擎，能够执行定义好的规则。
        *   **验收标准:**
            *   AC1: 规则引擎能在特定时机（例如，知识图谱更新后，或规划器调用时）被触发。
            *   AC2: 规则引擎能评估规则的`Antecedent` (SPARQL `WHERE`条件)。
            *   AC3: 对于条件满足的规则，规则引擎能执行其`Consequent` (SPARQL `CONSTRUCT`/`INSERT`/`UPDATE`)，并更新知识图谱。
            *   AC4: 规则可以有优先级，并在评估时予以考虑。

*   **2.4 执行状态图管理与日志**
    *   **FR-LOG-001: 执行状态图记录**
        *   **描述:** KCE应为每次流程执行的每个重要步骤（节点执行、规则应用）创建一个`kce:ExecutionStateNode`，并将这些状态节点链接起来形成执行状态图。
        *   **验收标准:**
            *   AC1: 每个`ExecutionStateNode`应记录时间戳、触发的操作（节点URI或规则URI）、状态（开始/成功/失败）、相关的输入/输出数据引用。
            *   AC2: 节点定义中可以标记其操作是否产生`kce:ExternalSideEffect`，此信息应记录在对应的状态节点上。
            *   AC3: 状态节点之间通过`kce:hasPreviousState`等关系链接，形成可追溯的路径。
            *   AC4: 所有状态节点信息存储在RDF知识库中。
    *   **FR-LOG-002: 人类可读的运行时I/O日志**
        *   **描述:** 对于每个节点执行实例，其接收的具体输入值和产生的具体输出值应以人类可读的格式（如JSON片段或格式化文本）记录下来。
        *   **验收标准:**
            *   AC1: 人类可读的I/O日志与对应的`ExecutionStateNode`关联（例如，存储在文件系统中，并在状态节点中有引用；或直接作为状态节点的文本属性）。
            *   AC2: CLI应提供命令查询指定执行实例或节点的此类日志。
    *   **FR-LOG-003: 错误记录**
        *   **描述:** 节点执行失败、规则应用错误或规划失败时，详细的错误信息（包括堆栈跟踪，如果适用）应被记录。
        *   **验收标准:**
            *   AC1: 错误信息与相关的`ExecutionStateNode`关联。
            *   AC2: CLI能查询这些错误信息。

*   **2.5 用户模式与交互 (CLI)**
    *   **FR-UI-001: 命令行接口 (CLI)**
        *   **描述:** KCE MVP应提供一个命令行接口作为用户与系统的主要交互方式。
        *   **验收标准:**
            *   AC1: 提供`kce load-defs <path>`命令加载YAML定义。
            *   AC2: 提供`kce solve-problem --target <target_desc_file> --initial-state <initial_state_file> [--mode <expert|user>]`命令提交问题并执行。
            *   AC3: 提供`kce query-log --run-id <run_id> [--node-id <node_id>]`命令查询执行日志和人类可读I/O。
            *   AC4: 提供`kce query-rdf --query "<sparql_query>"`命令执行任意SPARQL查询。
            *   AC5: (关联FR-LOG-001) 提供`kce trace-state-graph --run-id <run_id>`命令（简化版）展示执行状态序列。
    *   **FR-UI-002: 用户模式支持**
        *   **描述:** KCE应支持“领域用户模式”（全自动执行）和“专家模式”（允许干预）。
        *   **验收标准:**
            *   AC1: `solve-problem`命令可以通过`--mode`参数指定执行模式。
            *   AC2: 在“领域用户模式”下，流程从开始到结束全自动执行，若失败则报错并记录日志。
            *   AC3: (MVP简化专家模式) 在“专家模式”下，如果规划遇到多个同等优先级的路径或用户定义的“干预点”节点，可以暂停并向用户提示信息（CLI输出），用户可以通过输入简单指令（如选择路径编号，或提供修正参数的JSON）进行干预。MVP阶段的干预机制可以非常简化。
            *   AC4: 专家模式下的干预操作应被记录在执行状态图中。

*   **2.6 版本控制 (简化)**
    *   **FR-VER-001: 定义文件的版本标识**
        *   **描述:** 用户应能通过在其YAML定义文件（或文件名/目录结构约定）中包含版本号或标签，来管理不同版本的节点、规则、本体。
        *   **验收标准:**
            *   AC1: KCE在加载定义时，能够记录或允许用户指定这些定义的版本信息（如果提供）。
            *   AC2: KCE在执行或规划时，可以被配置为优先使用特定版本的定义（如果知识库中存在多个版本）。MVP阶段，可以简化为用户自行确保加载的是期望版本的定义集。

**3. 非功能性需求 (MVP简化)**

*   **NFR-001: 可用性 (定义者)**
    *   **描述:** YAML定义格式应相对清晰，有文档说明。错误提示应有助于定位问题。
*   **NFR-002: 可维护性**
    *   **描述:** 代码应遵循良好的模块化设计（如分层架构）。
*   **NFR-003: 可测试性**
    *   **描述:** 核心组件应易于进行单元测试和集成测试。
*   **NFR-004: 性能 (MVP放宽)**
    *   **描述:** 对于文档中定义的示例问题（如简化的壁板设计），系统应能在合理的时间内（例如，几分钟内）给出结果。不做严格的性能指标要求。
*   **NFR-005: 错误处理**
    *   **描述:** 系统在遇到预期错误（如无效输入、定义缺失）时应能优雅处理并给出明确提示，而不是直接崩溃。

**4. 核心工作流程示例 (以壁板设计为例)**

1.  **定义阶段 (领域专家):**
    1.  编写/更新领域本体 (`elevator_design.ttl`)，定义如`Panel`, `Joint`, `carWidth`等概念。
    2.  使用YAML编写节点定义 (`elevator_panel_nodes.yaml`)，例如`DeterminePanelCountNode`, `CalculatePanelDimensionsNode`, `CreatePanelJointsNode`，每个节点包含其Precondition, Effect, Input/Output, Implementation (Python脚本路径)。
    3.  使用YAML编写规则定义 (`elevator_panel_rules.yaml`)，例如`Rule_CheckPanelWidthConstraint`, `Rule_SwitchToFourPanelStrategy`。
    4.  使用CLI `kce load-defs` 将本体和定义加载到KCE知识库。
2.  **求解阶段 (领域用户/专家):**
    1.  准备问题实例JSON (`problem_case_X.json`)，包含初始轿厢尺寸，例如`{"carInterior": {"uri": "ex:MyCar", "width": 1500, "height": 2450}}`。
    2.  定义求解目标，例如一个SPARQL ASK查询文件 `target_goal.sparql` 内容为 `ASK { ex:MyCar kce_domain:hasRearWallAssembly [ kce:hasTotalCost ?anyCost ; kce:hasAllJointsGenerated true ] . }`。
    3.  执行CLI `kce solve-problem --target target_goal.sparql --initial-state problem_case_X.json --mode user`。
3.  **KCE内部处理:**
    1.  加载初始状态到RDF图。
    2.  规划器根据目标和当前知识图谱（包含节点库、规则库、实例数据），动态推导执行计划。
        *   例如，先执行`DeterminePanelCountNode`。
        *   执行后更新知识图谱。
        *   规则引擎应用`Rule_InstantiatePanels`。
        *   规划器继续规划，执行`CalculatePanelDimensionsNode`。
        *   如果触发`Rule_CheckPanelWidthConstraint`，知识图谱状态改变。
        *   规划器适应新状态，可能导致`Rule_SwitchToFourPanelStrategy`被应用，进而影响后续节点选择。
    3.  计划执行器按计划执行节点（调用Python脚本）和应用规则。
    4.  执行状态图被实时记录。人类可读I/O日志被生成。
4.  **结果获取与分析:**
    1.  CLI返回成功/失败状态。
    2.  用户使用`kce query-rdf`查询最终生成的壁板属性、成本、配合关系等。
    3.  用户使用`kce query-log`查看执行过程和I/O详情，用于调试或理解。

**5. 未来考虑 (MVP范围外)**

*   图形化用户界面
*   更高级的本体版本控制与扩展机制
*   复杂的性能优化
*   更完善的专家模式干预交互
*   分布式执行与知识库
*   安全性与权限管理
