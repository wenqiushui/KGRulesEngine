**Knowledge-CAD-Engine (KCE) - MVP 系统架构设计文档**

**文档版本:** 0.1
**日期:** 2025-06-07
**状态:** 初稿

**1. 引言**

*   **1.1 文档目的**
    本文档旨在详细描述Knowledge-CAD-Engine (KCE) MVP版本的系统架构。它将定义系统的主要组件、它们之间的关系和接口、数据流、技术选型以及关键的设计决策，为开发团队提供实现指南。
*   **1.2 系统概述**
    KCE是一个知识驱动的自动化引擎，其核心能力在于动态规划和执行基于领域知识（本体、节点、规则）的解决方案。MVP版本将通过命令行接口与用户交互，使用RDF作为核心知识表示，并支持通过YAML/JSON定义领域知识和问题。其独特的执行状态图管理机制将为流程追溯和调试提供支持。
*   **1.3 设计目标**
    *   **模块化:** 清晰分离的组件，易于独立开发和测试。
    *   **可扩展性:** 架构应能支持未来功能的添加（如更复杂的规划算法、GUI）。
    *   **可维护性:** 清晰的代码结构和文档。
    *   **核心功能验证:** 优先实现动态规划、规则驱动、节点执行、状态图管理等核心机制。
    *   **技术可行性:** 采用成熟且适合MVP阶段的技术栈。
*   **1.4 范围**
    本文档覆盖KCE MVP的软件架构，不包括详细的部署运维或用户界面设计（CLI除外）。

**2. 架构概述**

*   **2.1 分层架构**
    KCE采用分层架构，以实现关注点分离和模块化。主要层次包括：
    1.  **接口层 (Interface Layer):** 用户与KCE交互的入口。
    2.  **规划与推理核心层 (Planning & Reasoning Core Layer):** 负责动态规划和规则应用。
    3.  **执行层 (Execution Layer):** 负责实际执行计划中的操作和记录。
    4.  **知识层 (Knowledge Layer):** 负责存储和管理所有知识与数据。
    5.  **定义与转换层 (Definition & Transformation Layer):** 负责将用户定义转换为内部RDF表示。

    ```
    +-----------------------------------+
    |       接口层 (Interface Layer)    |  (CLI)
    +-----------------------------------+
         |          ^ (Commands | Results, Logs)
         V          |
    +-----------------------------------+
    |    规划与推理核心 (P&R Core)    |
    |  +-----------+  +-------------+ |
    |  | Planner   |  | Rule Engine | |
    |  +-----------+  +-------------+ |
    +-----------------------------------+
         |          ^ (Planning Req, Rule Exec Req | Plan, Knowledge Updates)
         |          | (Knowledge Queries | Knowledge)
         |----------|-------------------- (Interactions with Execution Layer)
         |          V
    +-----------------------------------+
    |       执行层 (Execution Layer)    |
    |  +---------------+  +-----------+ |
    |  | Plan Executor |  | Node Exec | |
    |  +---------------+  +-----------+ |
    |  +------------------------------+ |
    |  | Runtime State & I/O Logger   | |
    |  +------------------------------+ |
    +-----------------------------------+
         |          ^ (Exec Req | Exec Status, Logs, Provenance)
         |          | (Knowledge Queries/Updates | Knowledge)
         V          |
    +-----------------------------------+
    |       知识层 (Knowledge Layer)    |
    |  +-----------------+  +----------+ |
    |  | RDF Store &     |  | Human-    | |
    |  | OWL Reasoner    |  | Readable  | |
    |  +-----------------+  | Log Store | |
    |                       +----------+ |
    +-----------------------------------+
         |          ^ (SPARQL, Reasoning Triggers | RDF Data)
         V          | (RDF Triples to Load)
    +-----------------------------------+
    | 定义与转换层 (Def & Trans Layer)|  (YAML/JSON Parsers, RDF Converters)
    +-----------------------------------+
    ```

*   **2.2 核心数据流与控制流概述**
    1.  **定义加载:** 用户通过CLI将YAML/JSON定义文件提交给**定义与转换层**。该层解析文件，将其转换为RDF三元组，并加载到**知识层**的RDF Store中。
    2.  **问题求解请求:** 用户通过CLI提交问题（初始状态和目标）给**接口层**。
    3.  **规划启动:** 接口层将请求传递给**规划与推理核心层**的**Planner**。
    4.  **动态规划与推理:**
        *   **Planner** 从目标开始，查询**知识层**获取相关节点定义、规则定义和当前知识状态（包括OWL推理结果）。
        *   **Planner** 可能调用**Rule Engine**来应用规则，以派生新知识或改变状态，这些变更会更新到**知识层**。
        *   **Planner** 持续迭代，根据最新的知识图谱状态生成下一步的执行计划（可能是执行一个节点或应用一个规则）。
    5.  **计划执行:**
        *   **Planner** 将生成的（部分）计划传递给**执行层**的**Plan Executor**。
        *   **Plan Executor** 按照计划步骤：
            *   如果步骤是执行节点，则调用**Node Executor**。**Node Executor** 根据节点类型（MVP主要是Python脚本）调用相应的实现，并与**知识层**交互以获取输入和写回输出。
            *   如果步骤是应用规则，则调用**Rule Engine**（其效果是更新知识层）。
        *   **Runtime State & I/O Logger** 在每个步骤执行前后记录状态、输入输出到**知识层**（RDF溯源部分和人类可读日志部分）。
    6.  **循环与完成:** 节点执行或规则应用的结果会更新**知识层**。**Planner** 感知到这些变化，继续规划后续步骤，直到所有目标达成或无法找到可行路径。
    7.  **结果返回:** 最终结果（成功/失败状态，指向日志的引用）通过**接口层**返回给用户。

**3. 组件详解与接口定义**

*   **3.1 定义与转换层 (DTL)**
    *   **3.1.1 组件:**
        *   `YAMLParser`: 解析YAML格式的节点、规则、能力模板等定义文件。
        *   `JSONParser`: 解析JSON格式的问题实例参数。
        *   `RDFConverter`: 将解析后的Python对象（来自YAML/JSON）转换为符合KCE核心本体的RDF三元组。
    *   **3.1.2 对外接口 (供CLI或上层调用):**
        *   `load_definitions_from_path(path: str) -> LoadStatus`: 遍历路径下的YAML文件，解析并加载到知识层。
        *   `load_initial_state_from_json(json_data: str, base_uri: str) -> InitialStateGraph (rdflib.Graph)`: 解析问题实例JSON，转换为初始RDF图。
    *   **3.1.3 对内接口 (与知识层交互):**
        *   调用知识层的 `KnowledgeLayer.add_graph(graph: rdflib.Graph)` 或 `KnowledgeLayer.execute_sparql_update(update_string: str)`.

*   **3.2 知识层 (KL)**
    *   **3.2.1 组件:**
        *   `RDFStore`:
            *   **实现:** 使用 `rdflib` 库，后端为 `rdflib-sqlite` 持久化到SQLite文件 (`kce_knowledge_base.sqlite`)。
            *   **职责:** 存储所有RDF数据，提供SPARQL查询和更新接口。管理图的事务（rdflib的基本支持）。
        *   `OWLReasoner`:
            *   **实现:** 使用 `owlrl` 库，作用于`RDFStore`中的图。
            *   **职责:** 执行OWL RL推理。
        *   `HumanReadableLogStore`:
            *   **实现 (MVP):** 基于文件系统，在 `data/logs/<run_id>/` 目录下为每个重要执行事件（尤其是节点I/O）创建文本文件。
            *   **职责:** 存储人类可读的日志信息。
    *   **3.2.2 对外接口 (供其他层调用):**
        *   `execute_sparql_query(query_string: str) -> List[Dict] | bool | rdflib.Graph`: 执行SPARQL SELECT, ASK, CONSTRUCT, DESCRIBE。
        *   `execute_sparql_update(update_string: str) -> None`: 执行SPARQL INSERT, DELETE。
        *   `trigger_reasoning() -> None`: 触发OWL RL推理。
        *   `add_graph(graph: rdflib.Graph, context_uri: Optional[str] = None) -> None`: 添加RDF图到存储中。
        *   `get_graph(context_uri: Optional[str] = None) -> rdflib.Graph`: 获取RDF图。
        *   `store_human_readable_log(run_id: str, event_id: str, log_content: str) -> LogLocation`: 存储文本日志。
        *   `get_human_readable_log(log_location: LogLocation) -> Optional[str]`: 获取文本日志。

*   **3.3 执行层 (EL)**
    *   **3.3.1 组件:**
        *   `PlanExecutor`:
            *   **职责:** 接收来自Planner的执行计划（步骤序列），按序协调执行。管理当前执行会话的上下文（如全局序号生成器 - MVP简化）。
        *   `NodeExecutor`:
            *   **职责:** 负责具体原子节点的调用。根据节点定义中的`kce:invocationType`选择内部调用策略。
            *   **内部策略 (MVP):**
                *   `ScriptInvoker`: 调用Python脚本。准备参数，执行脚本，捕获输出/错误。
        *   `RuntimeStateAndIOLogger`:
            *   **职责:** 捕获节点和流程的运行时状态、实际输入输出。将其格式化为人类可读形式存入`HumanReadableLogStore`，并生成RDF溯源信息存入`RDFStore`。创建和链接`kce:ExecutionStateNode`。
    *   **3.3.2 对外接口 (供P&R Core调用):**
        *   `PlanExecutor.execute_plan(plan: ExecutionPlan, run_id: str, initial_graph: rdflib.Graph) -> ExecutionResult`:
            *   `ExecutionPlan`: 一个包含 `(operation_type: str ("node"|"rule"), operation_uri: str)` 的有序列表。
            *   `ExecutionResult`: 包含最终状态 (success/failure), 错误信息, run_id。
    *   **3.3.3 对内接口 (组件间):**
        *   `PlanExecutor` -> `NodeExecutor.execute_node(node_uri: str, run_id: str, current_input_graph: rdflib.Graph) -> NodeOutputGraph (rdflib.Graph)`
        *   `PlanExecutor/NodeExecutor` -> `RuntimeStateAndIOLogger.log_event(event: StateEvent)`
        *   `RuntimeStateAndIOLogger` -> `KnowledgeLayer.store_human_readable_log(...)` 和 `KnowledgeLayer.add_graph(...)` (用于存储RDF状态节点和溯源信息)

*   **3.4 规划与推理核心层 (P&R Core)**
    *   **3.4.1 组件:**
        *   `Planner`:
            *   **职责:** 核心动态规划逻辑。接收目标和初始状态，查询知识层，利用节点和规则定义，生成执行计划。持续适应知识图谱变化。
            *   **算法 (MVP):** 目标导向的搜索（如A*的简化版，或基于启发式的最佳优先搜索）。维护开放集（待扩展的规划路径/目标）和关闭集（已评估的）。
        *   `RuleEngine`:
            *   **职责:** 应用定义好的规则。
            *   **实现 (MVP):** 基于SPARQL。在规划器的特定阶段或知识图谱更新后被调用，执行所有条件满足的规则的`Consequent` (SPARQL CONSTRUCT/INSERT/UPDATE)。
    *   **3.4.2 对外接口 (供Interface Layer调用):**
        *   `Planner.solve(target_description: Target, initial_state_graph: rdflib.Graph, run_id: str, mode: str) -> ExecutionResult`:
            *   `Target`: 结构化的目标描述。
            *   内部会调用`PlanExecutor.execute_plan`。
    *   **3.4.3 对内接口 (组件间及与KL/EL交互):**
        *   `Planner` <-> `KnowledgeLayer` (大量SPARQL查询获取节点/规则定义、当前状态；更新规划过程中的中间状态或目标)。
        *   `Planner` -> `RuleEngine.apply_rules(current_graph: rdflib.Graph) -> UpdatedGraph`: （一种可能的交互方式，规则引擎返回更新后的图）。
        *   `Planner` -> `PlanExecutor.execute_plan` (传递生成的计划)。
        *   `RuleEngine` <-> `KnowledgeLayer` (查询规则条件，执行规则动作更新图谱)。

*   **3.5 接口层 (IL)**
    *   **3.5.1 组件 (MVP):**
        *   `CLIHandler`:
            *   **实现:** 使用 `click` 或 `argparse`。
            *   **职责:** 解析命令行参数，调用P&R Core或Knowledge Layer的相应接口，格式化并显示结果/日志。
    *   **3.5.2 对外接口 (用户通过命令行使用):**
        *   `kce load-defs <path>`
        *   `kce solve-problem --target <target_file> --initial-state <state_file> [--mode <expert|user>] [--run-id <id>]`
        *   `kce query-log --run-id <id> [--event-id <id>]`
        *   `kce query-rdf --query "<sparql>"`
        *   `kce trace-state-graph --run-id <id>`
    *   **3.5.3 对内接口 (调用P&R Core和Knowledge Layer):**
        *   调用 `Planner.solve`, `KnowledgeLayer.execute_sparql_query`, `KnowledgeLayer.get_human_readable_log` 等。

**4. 数据模型 (核心本体概述)**

*   KCE核心本体 (`kce_core_ontology.ttl`) 将定义以下主要概念及其关系 (详见PRD/FSD)：
    *   `kce:Entity`, `kce:Concept`, `kce:Property`
    *   `kce:Node`, `kce:AtomicNode`, `kce:CompositeNode` (MVP可能简化CompositeNode的规划)
    *   `kce:InputParameter`, `kce:OutputParameter`, `kce:Precondition`, `kce:Effect`
    *   `kce:ImplementationDetail` (包含 `kce:scriptPath`, `kce:invocationType` 等)
    *   `kce:Rule`, `kce:Antecedent`, `kce:Consequent`
    *   `kce:CapabilityTemplate`, `kce:InputInterface`, `kce:OutputInterface`, `kce:implementsCapability`, `kce:capabilityMapping`
    *   `kce:ExecutionRun` (关联 `run_id`)
    *   `kce:ExecutionStateNode` (属性: `kce:timestamp`, `kce:triggeredByOperation` (Node/Rule URI), `kce:status` (enum: Started, Succeeded, Failed), `kce:inputDataSnapshot` (ref), `kce:outputDataSnapshot` (ref), `kce:hasPreviousState` (ref), `kce:isSideEffectState` (boolean), `kce:humanReadableLogLocation` (ref))
    *   `kce:Goal`, `kce:TargetDescription`
    *   PROV-O的子集用于数据溯源 (`prov:Activity`, `prov:Entity`, `prov:wasGeneratedBy`, `prov:used`).

**5. 技术选型**

*   **Python 3.8+:** 主开发语言。
*   **rdflib:** RDF数据处理。
*   **rdflib-sqlite:** RDF持久化存储后端。
*   **owlrl:** OWL RL推理。
*   **PyYAML:** 解析YAML配置文件。
*   **click / argparse:** 构建命令行接口。
*   **pytest:** 自动化测试框架。
*   **Git:** 版本控制。

**6. 关键设计决策 (MVP)**

*   **动态规划优先:** 架构核心围绕支持动态、持续的规划。
*   **知识图谱驱动:** 所有决策和状态变更均通过RDF知识图谱反映和驱动。
*   **执行状态图管理:** 作为核心机制支持追溯、调试和“类回退”操作。
*   **YAML/JSON作为主要定义格式:** 兼顾人类可读性和机器可处理性。
*   **Python脚本作为节点实现的主要方式:** 简单直接，易于领域专家编写。
*   **CLI作为主要交互界面:** 快速验证核心功能。
*   **专家模式简化:** MVP的专家模式干预点可以非常基础，例如在规划失败时允许用户查看当前状态图并手动修改部分RDF数据后重试，或选择不同的初始目标。

**7. 未来扩展考虑 (不在MVP范围，但架构应有所预留)**

*   图形化用户界面 (流程设计、监控、结果展示)。
*   更高级的规划算法和AI集成。
*   支持更多类型的节点实现（如REST API调用、Docker容器等）。
*   分布式知识库和执行引擎。
*   完善的本体和知识库版本管理。
*   详细的权限和安全控制。
