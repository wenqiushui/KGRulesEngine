from rdflib import Graph, URIRef, Literal
from graph_pattern_engine import GraphPatternEngine
import json

def test_wall_panel_scenarios():
    # 初始化引擎
    engine = GraphPatternEngine()
    
    # 加载知识
    engine.load_ontology("ontology.ttl")
    engine.load_rules("rules.ttl")
    engine.load_templates("templates.ttl")
    
    print("=== 测试1: 初始设计 - 配合关系生成 ===")
    context = {}
    result = engine.query("http://elevator.com/ontology#JointGeneration", context)
    joints = json.loads(result["_:result"]["joints"].replace("'", '"'))
    print("生成的配合关系:")
    print(json.dumps({"joints": joints}, indent=2, ensure_ascii=False))
    
    print("\n=== 测试2: 初始设计 - 尺寸计算 ===")
    context = {
        "cabinet_height": 2450,
        "cabinet_width": 1500
    }
    result = engine.query("http://elevator.com/ontology#DimensionCalculation", context)
    dimensions = json.loads(f"[{result['_:result']['dimensions']}]".replace("'", '"'))
    print("壁板尺寸:")
    print(json.dumps({"轿厢后壁板尺寸": dimensions}, indent=2, ensure_ascii=False))
    
    print("\n=== 测试3: 初始设计 - 成本计算 ===")
    result = engine.query("http://elevator.com/ontology#CostCalculation", context)
    costs = json.loads(f"[{result['_:result']['costs']}]".replace("'", '"'))
    print("壁板成本:")
    print(json.dumps(costs, indent=2, ensure_ascii=False))
    
    print("\n=== 测试4: 设计变更 - 宽度增加 ===")
    context = {
        "cabinet_height": 2450,
        "cabinet_width": 2200  # 宽度超过2100，触发变更
    }
    print("应用设计变更...")
    result = engine.query("http://elevator.com/ontology#DesignChange", context)
    
    print("\n变更后 - 尺寸计算:")
    result = engine.query("http://elevator.com/ontology#DimensionCalculation", context)
    dimensions = json.loads(f"[{result['_:result']['dimensions']}]".replace("'", '"'))
    print(json.dumps({"轿厢后壁板尺寸": dimensions}, indent=2, ensure_ascii=False))
    
    print("\n变更后 - 配合关系生成:")
    result = engine.query("http://elevator.com/ontology#JointGeneration", context)
    joints = json.loads(result["_:result"]["joints"].replace("'", '"'))
    print(json.dumps({"joints": joints}, indent=2, ensure_ascii=False))
    
    print("\n变更后 - 成本计算:")
    result = engine.query("http://elevator.com/ontology#CostCalculation", context)
    costs = json.loads(f"[{result['_:result']['costs']}]".replace("'", '"'))
    print(json.dumps(costs, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    test_wall_panel_scenarios()
