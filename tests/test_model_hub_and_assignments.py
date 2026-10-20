import unittest
from fastapi.testclient import TestClient

from src.config import config_manager
from main import app
from src.auth import generate_token
from src.active_reply import parse_decision_response


class TestModelHubAndAssignments(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.token = generate_token("admin")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_01_decision_parser_robustness(self):
        """测试决策解析器对各种劣质/异常JSON输出的超强容错。"""
        raw_1 = '```json\n{\n  "should_reply": true,\n  "confidence": 0.88,\n  "reason": "聊日常",\n}\n```'
        sr, conf, reason, _ = parse_decision_response(raw_1)
        self.assertTrue(sr)
        self.assertAlmostEqual(conf, 0.88, places=2)

        raw_2 = "<think>分析中...\n{'should_reply': True, 'confidence': 0.75, 'reason': '画画话题'}"
        sr, conf, reason, _ = parse_decision_response(raw_2)
        self.assertTrue(sr)
        self.assertAlmostEqual(conf, 0.75, places=2)

        raw_3 = "经过评估：should_reply: 是，置信度: 0.91，理由: 讨论美食"
        sr, conf, reason, _ = parse_decision_response(raw_3)
        self.assertTrue(sr)
        self.assertAlmostEqual(conf, 0.91, places=2)

    def test_02_detect_dimension_builtin(self):
        """测试内置模型的维度探测端点。"""
        resp = self.client.post(
            "/api/llm/detect_dimension",
            json={"provider_id": "builtin", "model_name": "bge-small-zh-v1.5"},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["dimension"], 512)
        self.assertEqual(data["status"], "success")

    def test_03_model_assignments_lifecycle(self):
        """测试五大功能分配的查询与保存。"""
        resp = self.client.get("/api/llm/assignments", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("replyer", data)
        self.assertIn("planner", data)
        self.assertIn("embedding", data)
        self.assertIn("vlm", data)
        self.assertIn("utils", data)

        save_resp = self.client.post(
            "/api/llm/assignments",
            json={
                "planner": {"strategy": "fixed", "max_tokens": 350, "temperature": 0.15},
                "embedding": {"model_id": "builtin/bge-small-zh-v1.5", "dimension": 512},
            },
            headers=self.headers,
        )
        self.assertEqual(save_resp.status_code, 200)
        saved_data = save_resp.json()
        self.assertEqual(saved_data["status"], "success")
        self.assertEqual(saved_data["assignments"]["planner"]["max_tokens"], 350)
        self.assertEqual(saved_data["assignments"]["embedding"]["dimension"], 512)

    def test_04_model_hub_with_embedding(self):
        """测试模型库中包含内置向量模型及自定义类型。"""
        resp = self.client.get("/api/llm/hub", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        items = resp.json()["items"]
        
        builtin_item = next((it for it in items if "bge-small-zh-v1.5" in it["id"]), None)
        self.assertIsNotNone(builtin_item)
        self.assertEqual(builtin_item["model_type"], "embedding")
        self.assertEqual(builtin_item["dimension"], 512)


if __name__ == "__main__":
    unittest.main()
