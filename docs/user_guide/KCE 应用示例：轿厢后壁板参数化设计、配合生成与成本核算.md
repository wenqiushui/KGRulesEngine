**KCE 应用示例：轿厢后壁板参数化设计、配合生成与成本核算 - 领域知识与需求详述**

**文档版本:** 1.0
**日期:** 2025-06-07
**贡献者:** (用户/领域专家名称)
**审阅者:** (产品经理/架构师名称)

**1. 概述与目标**

本文档旨在详细描述轿厢后壁板设计、配合关系生成、成本核算以及相关变更规则的领域知识和预期行为。这些信息将作为Knowledge-CAD-Engine (KCE) 系统构建相应自动化解决方案的基础。KCE的目标是根据给定的轿厢内部尺寸，自动完成以下任务：

*   确定后壁板的组成数量。
*   计算每块壁板的详细尺寸（宽度、高度、厚度、折弯高度）。
*   确定每块壁板的加强筋数量和螺栓孔数量。
*   生成后壁板之间的配合关系记录。
*   计算每块壁板的成本以及后壁总成的总成本。
*   在特定条件下（如轿厢宽度变化），能够自动适应设计变更。

**2. 核心实体与属性 (本体概念)**

*   **`ElevatorCar` (电梯轿厢)**
    *   `carInteriorWidth` (轿厢内部宽度): 整数, 单位 mm. (例如: 1500)
    *   `carInteriorHeight` (轿厢内部高度): 整数, 单位 mm. (例如: 2450)
*   **`RearWallAssembly` (后壁总成)**
    *   `assemblyWidth` (总成宽度): 整数, 单位 mm. (等于 `carInteriorWidth`)
    *   `assemblyHeight` (总成高度): 整数, 单位 mm. (等于 `carInteriorHeight`)
    *   `panelCount` (壁板数量): 整数 (3 或 4).
    *   `panelArrangementStrategy` (壁板布局策略): 枚举型 (例如: "Standard3Panel", "Wide4Panel_LR500_MidEvenSplit").
    *   `totalMaterialCost` (总材料成本): 浮点数.
    *   `totalProcessingCost` (总加工成本): 浮点数.
    *   `totalAssemblyCost` (总装配成本): 浮点数.
    *   `hasPanel` (拥有壁板): 关系, 指向多个 `Panel` 实例.
    *   `hasJoint` (拥有配合): 关系, 指向多个 `Joint` 实例.
*   **`Panel` (壁板 - 可作为父类概念)**
    *   `panelName` (壁板名称): 字符串 (例如: "左后壁", "中间后壁", "中间后壁001", "右后壁").
        *   *命名规则:* 用户提供三维模型的原始名称。如果KCE需要实例化多个完全相同的三维模型（如4块壁板时的中间两块），第一个模型使用原始名称，后续模型在原始名称后附加三位数的序列号，从"001"开始 (例如, "中间后壁", "中间后壁001")。此命名规则由用户或外部脚本在提供模型实例时保证，KCE不负责此三维实例命名。
    *   `panelType` (壁板类型): 枚举型 (例如: "LeftRear", "MiddleRear", "RightRear").
    *   `width` (宽度): 整数, 单位 mm.
    *   `height` (高度): 整数, 单位 mm.
    *   `thickness` (厚度): 浮点数, 单位 mm (例如: 1.3, 1.5).
    *   `bendHeight` (折弯高度): 整数, 单位 mm (例如: 25, 34).
    *   `maxAllowableWidth` (单块最大许用宽度): 整数, 单位 mm (固定值: 700).
    *   `boltHoleCount` (螺栓孔数量): 整数.
    *   `boltHoleDiameter` (螺栓孔直径): 整数, 单位 mm (固定值: 10).
    *   `stiffenerCount` (加强筋数量): 整数.
    *   `materialCost` (材料成本): 浮点数.
    *   `processingCost` (加工成本): 浮点数.
    *   `panelTotalCost` (单块壁板总成本): 浮点数.
    *   `faceSelectionMethods` (面选择方法集): 结构化数据，包含各标准面的选择方法。
        *   `innerFace`: 字符串 (例如: "parall_xz_nearest_face")
        *   `outerFace`: 字符串 (例如: "parall_xz_farthest_face")
        *   `topFace`: 字符串 (例如: "parall_xy_farthest_face")
        *   `bottomFace`: 字符串 (例如: "parall_xy_nearest_face")
        *   `leftFace`: 字符串 (例如: "parall_yz_nearest_face")
        *   `rightFace`: 字符串 (例如: "parall_yz_farthest_face")
        *   *注:* 所有面选择方法统一使用下划线 `_` 作为分隔符。
*   **`Joint` (配合)**
    *   `jointName` (配合名称): 字符串.
        *   *命名规则:* "连接对象1名称-连接对象2名称-配合类型"。如果存在`part1_n`, `part2_n`, `type` 完全相同的配合，则后续配合的名称在此基础上增加全局唯一的三位数的序列号，从"001"开始 (例如: "左后壁-中间后壁-平齐", "左后壁-中间后壁-平齐001")。
    *   `jointType` (配合类型): 枚举型 ("平齐", "接触").
    *   `part1Name` (第一个配合对象名称): 字符串 (引用 `Panel.panelName`).
    *   `part1FaceSelectionMethod` (第一个配合对象面选择方法): 字符串 (引用 `Panel.faceSelectionMethods` 中的值).
    *   `part2Name` (第二个配合对象名称): 字符串 (引用 `Panel.panelName`).
    *   `part2FaceSelectionMethod` (第二个配合对象面选择方法): 字符串 (引用 `Panel.faceSelectionMethods` 中的值).

**3. 业务规则与计算逻辑**

*   **3.1 后壁板数量与布局策略确定**
    *   **Rule-PNLCOUNT-001 (最大宽度约束):** 单块 `Panel` 的 `maxAllowableWidth` 为 700 mm。
    *   **Rule-PNLCOUNT-002 (默认3块策略):**
        *   当 `ElevatorCar.carInteriorWidth` <= 2100 mm 时，`RearWallAssembly.panelCount` 为 3。
        *   `RearWallAssembly.panelArrangementStrategy` 为 "Standard3Panel"。
    *   **Rule-PNLCOUNT-003 (触发4块策略):** 如果基于默认策略（如3块）计算出的任何一块 `Panel.width` > `Panel.maxAllowableWidth` (700 mm)，则必须增加 `RearWallAssembly.panelCount`。
    *   **Rule-PNLCOUNT-004 (强制4块策略):**
        *   当 `ElevatorCar.carInteriorWidth` > 2100 mm 且 <= 2800 mm 时，`RearWallAssembly.panelCount` 为 4。
        *   `RearWallAssembly.panelArrangementStrategy` 为 "Wide4Panel_LR500_MidEvenSplit"。
    *   *KCE实现注意:* "默认按3块计算，到检查节点触发重新规划" 是用户期望的一种流程。KCE需要能支持这种模式：即先按某一策略计算，然后一个“检查节点”或“检查规则”根据Rule-PNLCOUNT-001和Rule-PNLCOUNT-003判断是否需要调整。如果需要调整，知识图谱中的状态（如`panelArrangementStrategy`）会改变，KCE的规划器会基于新状态选择后续的计算节点。

*   **3.2 壁板尺寸计算 (`Panel.width`, `Panel.height`)**
    *   **Rule-DIM-001 (高度):** 所有 `Panel.height` 等于 `ElevatorCar.carInteriorHeight`。
    *   **Rule-DIM-002 (3块壁板宽度 - "Standard3Panel" 策略):**
        *   `Panel_MiddleRear.width` = 700 mm.
        *   `Panel_LeftRear.width` = `Panel_RightRear.width` = (`ElevatorCar.carInteriorWidth` - 700) / 2.
        *   如果 (`ElevatorCar.carInteriorWidth` - 700) 不能被2整除，多余的1mm分配给 `Panel_MiddleRear.width` (即，先计算左右，中间取剩余)。
    *   **Rule-DIM-003 (4块壁板宽度 - "Wide4Panel_LR500_MidEvenSplit" 策略):**
        *   `Panel_LeftRear.width` = `Panel_RightRear.width` = 500 mm.
        *   `Panel_MiddleRear1.width` = `Panel_MiddleRear2.width` = (`ElevatorCar.carInteriorWidth` - 500 - 500) / 2.
        *   如果 (`ElevatorCar.carInteriorWidth` - 1000) 不能被2整除，多余的1mm分配给其中一个中间壁板（例如，第一个 "中间后壁"）。

*   **3.3 壁板厚度与折弯高度计算 (`Panel.thickness`, `Panel.bendHeight`)**
    *   **Rule-THICK-001:**
        *   如果 `ElevatorCar.carInteriorHeight` <= 2300 mm:
            *   `Panel.thickness` = 1.3 mm.
            *   `Panel.bendHeight` = 25 mm.
        *   如果 `ElevatorCar.carInteriorHeight` > 2300 mm:
            *   `Panel.thickness` = 1.5 mm.
            *   `Panel.bendHeight` = 34 mm.

*   **3.4 螺栓孔计算 (`Panel.boltHoleCount`)**
    *   **Rule-BOLT-001 (直径):** `Panel.boltHoleDiameter` = 10 mm.
    *   **Rule-BOLT-002 (数量与布局):**
        *   螺栓孔在 `Panel` 的左侧面和右侧面对称开孔（如果该面需要与其他壁板连接）。
        *   每侧的螺孔数量 = `ceil(Panel.height / 300)`。 (注意：示例中是“间距不超过300”，这里明确为计算公式)
        *   `Panel.boltHoleCount` = 2 * `ceil(Panel.height / 300)` (指一个壁板上需要与相邻壁板连接的总螺孔数，例如中间壁板左右两侧都有)。对于仅一侧连接的壁板（最左、最右），则是 `ceil(Panel.height / 300)`。 *<-- 此处需PM与用户确认，是单侧算还是总数，示例中的14更像是总数的一半或单侧数量乘以2，再乘以连接面数。我们先按“每条连接边上的螺孔数”来理解，一个panel的总螺孔数是其参与连接的边的螺孔数之和。为简化，这里假定`boltHoleCount`是指一个Panel实例上**所有**用于连接的螺孔总数。*
        *   更精确定义：对于一个Panel，其左侧连接边螺孔数 `N_left = ceil(Panel.height / 300)` (如果左侧有连接)，右侧连接边螺孔数 `N_right = ceil(Panel.height / 300)` (如果右侧有连接)。`Panel.boltHoleCount = N_left + N_right`。
        *   开孔从壁板底部边缘向上开始计算第一个孔位，后续孔按最大不超过300mm的间距均布。

*   **3.5 加强筋计算 (`Panel.stiffenerCount`)**
    *   **Rule-STIFF-001:**
        *   如果 `Panel.width` <= 300 mm: `Panel.stiffenerCount` = 0.
        *   如果 300 mm < `Panel.width` <= 500 mm: `Panel.stiffenerCount` = 1.
        *   如果 `Panel.width` > 500 mm: `Panel.stiffenerCount` = 2.

*   **3.6 壁板配合生成 (`Joint` 实例)**
    *   **Rule-JOINT-001 (配合面定义):** 每个`Panel`实例都具有`faceSelectionMethods`属性，其值如下：
        ```json
        {
          "innerFace": "parall_xz_nearest_face",
          "outerFace": "parall_xz_farthest_face",
          "topFace": "parall_xy_farthest_face",
          "bottomFace": "parall_xy_nearest_face",
          "leftFace": "parall_yz_nearest_face",
          "rightFace": "parall_yz_farthest_face"
        }
        ```
    *   **Rule-JOINT-002 (内面平齐):**
        *   `Panel_LeftRear.innerFace` 与 `Panel_MiddleRear(s).innerFace` 平齐。
        *   `Panel_LeftRear.innerFace` 与 `Panel_RightRear.innerFace` 平齐。
        *   (推广：所有后壁板的内面相互平齐，通常以最左侧壁板的内面为基准。)
    *   **Rule-JOINT-003 (底面平齐):**
        *   `Panel_LeftRear.bottomFace` 与 `Panel_MiddleRear(s).bottomFace` 平齐。
        *   `Panel_LeftRear.bottomFace` 与 `Panel_RightRear.bottomFace` 平齐。
        *   (推广：所有后壁板的底面相互平齐，通常以最左侧壁板的底面为基准。)
    *   **Rule-JOINT-004 (相邻面接触 - 3块壁板):**
        *   `Panel_LeftRear.rightFace` 与 `Panel_MiddleRear.leftFace` 接触。
        *   `Panel_MiddleRear.rightFace` 与 `Panel_RightRear.leftFace` 接触。
    *   **Rule-JOINT-005 (相邻面接触 - 4块壁板):**
        *   `Panel_LeftRear.rightFace` 与 `Panel_MiddleRear1.leftFace` 接触。
        *   `Panel_MiddleRear1.rightFace` 与 `Panel_MiddleRear2.leftFace` 接触。
        *   `Panel_MiddleRear2.rightFace` 与 `Panel_RightRear.leftFace` 接触。
    *   **Rule-JOINT-006 (配合记录参数):** 每个`Joint`记录包含 `jointName`, `jointType`, `part1Name`, `part1FaceSelectionMethod`, `part2Name`, `part2FaceSelectionMethod`。
    *   **Rule-JOINT-007 (配合名称序号):** 如果生成的配合中，`part1Name`, `part2Name`, `jointType`完全相同，则从第二个此类配合开始，在原配合名称后附加全局唯一的从"001"开始的三位数序号。

*   **3.7 成本计算**
    *   **Rule-COST-001 (材料成本 - `Panel.materialCost`):**
        *   如果 `Panel.thickness` == 1.3:
            *   如果 `Panel.width` <= 500 mm: `Panel.materialCost` = 400.
            *   如果 `Panel.width` > 500 mm: `Panel.materialCost` = 600.
        *   如果 `Panel.thickness` == 1.5:
            *   如果 `Panel.width` <= 500 mm: `Panel.materialCost` = 500.
            *   如果 `Panel.width` > 500 mm: `Panel.materialCost` = 800.
    *   **Rule-COST-002 (加工成本 - `Panel.processingCost`):**
        *   折弯成本: 每块壁板固定 30.
        *   开孔成本: 每孔 0.5.
        *   `Panel.processingCost` = 30 + (`Panel.boltHoleCount` * 0.5).
    *   **Rule-COST-003 (单板总成本 - `Panel.panelTotalCost`):**
        *   `Panel.panelTotalCost` = `Panel.materialCost` + `Panel.processingCost`.
    *   **Rule-COST-004 (总装配成本 - `RearWallAssembly.totalAssemblyCost`):**
        *   `RearWallAssembly.totalAssemblyCost` = Sum of all `Panel.panelTotalCost` for panels in the assembly.
        *   (也可以分别累加总材料成本和总加工成本)。

*   **3.8 错误处理**
    *   **Rule-ERR-001:** 如果任何计算导致不合理的物理值（如负宽度、负成本），或输入参数超出预定范围（如轿厢宽度过小无法满足最小壁板宽度），KCE应报错并终止当前求解过程。错误信息应清晰指出问题所在。

**4. 数据示例与预期输出**

*   **4.1 场景一: 3块标准壁板**
    *   **输入:** `ElevatorCar { carInteriorWidth: 1500, carInteriorHeight: 2450 }`
    *   **预期关键输出 (Panel Dimensions - JSON):**
        ```json
        {
          "RearWallAssembly_URI": { // URI由KCE生成或用户指定
            "panelCount": 3,
            "panelArrangementStrategy": "Standard3Panel",
            "panels": [
              {"panelName": "左后壁", "panelType": "LeftRear", "width": 400, "height": 2450, "thickness": 1.5, "bendHeight": 34, "boltHoleCount": 9, "stiffenerCount": 1, "materialCost": 500, "processingCost": 30 + 9*0.5, "panelTotalCost": 534.5},
              {"panelName": "中间后壁", "panelType": "MiddleRear", "width": 700, "height": 2450, "thickness": 1.5, "bendHeight": 34, "boltHoleCount": 18, "stiffenerCount": 2, "materialCost": 800, "processingCost": 30 + 18*0.5, "panelTotalCost": 839.0},
              {"panelName": "右后壁", "panelType": "RightRear", "width": 400, "height": 2450, "thickness": 1.5, "bendHeight": 34, "boltHoleCount": 9, "stiffenerCount": 1, "materialCost": 500, "processingCost": 30 + 9*0.5, "panelTotalCost": 534.5}
            ],
            "totalAssemblyCost": 1908.0 // 534.5 + 839.0 + 534.5
          }
        }
        ```
        *螺孔数计算修正: `ceil(2450/300) = ceil(8.16) = 9`。左右壁板单侧连接，9孔。中间壁板双侧连接，18孔。*
    *   **预期关键输出 (Joints - JSON):** (如之前用户提供的3块板配合JSON，键名用`part1Name`, `part1FaceSelectionMethod`等，面选择方法用下划线)
        ```json
        {
          "RearWallAssembly_URI": { // URI与上面对应
            "joints": [
              { "jointName": "左后壁-中间后壁-平齐", "jointType": "平齐", "part1Name": "左后壁", "part1FaceSelectionMethod": "parall_xz_nearest_face", "part2Name": "中间后壁", "part2FaceSelectionMethod": "parall_xz_nearest_face" },
              { "jointName": "左后壁-右后壁-平齐", "jointType": "平齐", "part1Name": "左后壁", "part1FaceSelectionMethod": "parall_xz_nearest_face", "part2Name": "右后壁", "part2FaceSelectionMethod": "parall_xz_nearest_face" },
              { "jointName": "左后壁-中间后壁-平齐001", "jointType": "平齐", "part1Name": "左后壁", "part1FaceSelectionMethod": "parall_xy_nearest_face", "part2Name": "中间后壁", "part2FaceSelectionMethod": "parall_xy_nearest_face" },
              { "jointName": "左后壁-右后壁-平齐001", "jointType": "平齐", "part1Name": "左后壁", "part1FaceSelectionMethod": "parall_xy_nearest_face", "part2Name": "右后壁", "part2FaceSelectionMethod": "parall_xy_nearest_face" },
              { "jointName": "左后壁-中间后壁-接触", "jointType": "接触", "part1Name": "左后壁", "part1FaceSelectionMethod": "parall_yz_farthest_face", "part2Name": "中间后壁", "part2FaceSelectionMethod": "parall_yz_nearest_face" },
              { "jointName": "中间后壁-右后壁-接触", "jointType": "接触", "part1Name": "中间后壁", "part1FaceSelectionMethod": "parall_yz_farthest_face", "part2Name": "右后壁", "part2FaceSelectionMethod": "parall_yz_nearest_face" }
            ]
          }
        }
        ```

*   **4.2 场景二: 4块壁板 (因宽度 > 2100)**
    *   **输入:** `ElevatorCar { carInteriorWidth: 2200, carInteriorHeight: 2450 }`
    *   **预期关键输出 (Panel Dimensions - JSON):**
        ```json
        {
          "RearWallAssembly_URI": {
            "panelCount": 4,
            "panelArrangementStrategy": "Wide4Panel_LR500_MidEvenSplit",
            "panels": [
              {"panelName": "左后壁", "panelType": "LeftRear", "width": 500, "height": 2450, "thickness": 1.5, "bendHeight": 34, "boltHoleCount": 9, "stiffenerCount": 1, "materialCost": 500, "processingCost": 34.5, "panelTotalCost": 534.5},
              {"panelName": "中间后壁", "panelType": "MiddleRear", "width": 600, "height": 2450, "thickness": 1.5, "bendHeight": 34, "boltHoleCount": 18, "stiffenerCount": 2, "materialCost": 800, "processingCost": 39.0, "panelTotalCost": 839.0},
              {"panelName": "中间后壁001", "panelType": "MiddleRear", "width": 600, "height": 2450, "thickness": 1.5, "bendHeight": 34, "boltHoleCount": 18, "stiffenerCount": 2, "materialCost": 800, "processingCost": 39.0, "panelTotalCost": 839.0},
              {"panelName": "右后壁", "panelType": "RightRear", "width": 500, "height": 2450, "thickness": 1.5, "bendHeight": 34, "boltHoleCount": 9, "stiffenerCount": 1, "materialCost": 500, "processingCost": 34.5, "panelTotalCost": 534.5}
            ],
            "totalAssemblyCost": 2747.0 // 534.5 * 2 + 839.0 * 2
          }
        }
        ```
    *   **预期关键输出 (Joints - JSON):** (如之前补充的4块板配合JSON，键名和面选择方法已修正)
        ```json
        {
          "RearWallAssembly_URI": {
            "joints": [
                { "jointName": "左后壁-中间后壁-平齐", "jointType": "平齐", "part1Name": "左后壁", "part1FaceSelectionMethod": "parall_xz_nearest_face", "part2Name": "中间后壁", "part2FaceSelectionMethod": "parall_xz_nearest_face"},
                { "jointName": "左后壁-中间后壁001-平齐", "jointType": "平齐", "part1Name": "左后壁", "part1FaceSelectionMethod": "parall_xz_nearest_face", "part2Name": "中间后壁001", "part2FaceSelectionMethod": "parall_xz_nearest_face"},
                { "jointName": "左后壁-右后壁-平齐", "jointType": "平齐", "part1Name": "左后壁", "part1FaceSelectionMethod": "parall_xz_nearest_face", "part2Name": "右后壁", "part2FaceSelectionMethod": "parall_xz_nearest_face"},
                { "jointName": "左后壁-中间后壁-平齐001", "jointType": "平齐", "part1Name": "左后壁", "part1FaceSelectionMethod": "parall_xy_nearest_face", "part2Name": "中间后壁", "part2FaceSelectionMethod": "parall_xy_nearest_face"},
                { "jointName": "左后壁-中间后壁001-平齐001", "jointType": "平齐", "part1Name": "左后壁", "part1FaceSelectionMethod": "parall_xy_nearest_face", "part2Name": "中间后壁001", "part2FaceSelectionMethod": "parall_xy_nearest_face"},
                { "jointName": "左后壁-右后壁-平齐001", "jointType": "平齐", "part1Name": "左后壁", "part1FaceSelectionMethod": "parall_xy_nearest_face", "part2Name": "右后壁", "part2FaceSelectionMethod": "parall_xy_nearest_face"},
                { "jointName": "左后壁-中间后壁-接触", "jointType": "接触", "part1Name": "左后壁", "part1FaceSelectionMethod": "parall_yz_farthest_face", "part2Name": "中间后壁", "part2FaceSelectionMethod": "parall_yz_nearest_face"},
                { "jointName": "中间后壁-中间后壁001-接触", "jointType": "接触", "part1Name": "中间后壁", "part1FaceSelectionMethod": "parall_yz_farthest_face", "part2Name": "中间后壁001", "part2FaceSelectionMethod": "parall_yz_nearest_face"},
                { "jointName": "中间后壁001-右后壁-接触", "jointType": "接触", "part1Name": "中间后壁001", "part1FaceSelectionMethod": "parall_yz_farthest_face", "part2Name": "右后壁", "part2FaceSelectionMethod": "parall_yz_nearest_face"}
              ]
          }
        }
        ```

*   **4.3 其他边界和错误场景数据示例...** (如前讨论，PM应详细列出)

**5. KCE 交互期望 (专家模式与用户模式)**

*   **领域用户模式:** 用户提交轿厢尺寸，KCE自动完成所有计算和配合生成，输出最终结果和日志。若发生不可处理的错误（如输入参数无效），则报错退出。
*   **专家模式 (MVP简化):** 如果KCE在规划或执行中遇到 Rule-PNLCOUNT-003（例如，默认3块策略导致单板超宽），系统可以：
    1.  记录当前状态和检测到的问题到执行状态图。
    2.  暂停执行，并在CLI提示用户：“检测到单板宽度超限，建议切换到4板策略。是否继续？(Y/N/Abort)”。
    3.  如果用户输入Y，KCE知识图谱中的`panelArrangementStrategy`被更新，规划器基于新策略继续。
    4.  如果用户输入N（或提供其他修正指令，MVP可能不支持复杂指令），用户需要知道如何手动修改知识图谱（通过SPARQL或重新加载修改后的定义）或中止。
    5.  所有干预和决策都应记录在执行状态图中。
