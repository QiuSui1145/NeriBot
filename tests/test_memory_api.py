import requests
import json
import time

BASE_URL = "http://127.0.0.1:8088"
session = requests.Session()

def test_memory_flow():
    # 1. Login
    import os
    admin_pw = "admin"
    if os.path.exists("config/config.json"):
        try:
            with open("config/config.json", "r", encoding="utf-8") as f:
                admin_pw = json.load(f).get("security", {}).get("admin_password", "admin")
        except Exception:
            pass
    login_res = session.post(f"{BASE_URL}/api/auth/login", json={"username": "admin", "password": admin_pw})
    print("1. Login status:", login_res.status_code, login_res.json())
    assert login_res.status_code == 200

    # 2. Get Stats
    stats_res = session.get(f"{BASE_URL}/api/memory/stats")
    print("2. Memory stats:", stats_res.status_code, stats_res.json())
    assert stats_res.status_code == 200
    assert stats_res.json()["status"] == "ok"
    assert stats_res.json()["stats"]["dimension"] == 512

    # 3. Full Link Self Test
    selftest_res = session.get(f"{BASE_URL}/api/memory/selftest")
    print("3. Memory selftest:", selftest_res.status_code, selftest_res.json())
    assert selftest_res.status_code == 200
    assert selftest_res.json()["report"]["status"] == "healthy"

    # 4. Add Memory
    add_res = session.post(f"{BASE_URL}/api/memory/add", json={
        "user_id": "10001",
        "content": "[测试/诊断] 哥哥今天带音理去吃了海盐冰淇淋，甜丝丝的真让人开心。",
        "mem_type": "episode",
        "importance": 4.5
    })
    print("4. Add memory:", add_res.status_code, add_res.json())
    assert add_res.status_code == 200
    mem_id = add_res.json()["id"]

    # 5. List Memories
    list_res = session.get(f"{BASE_URL}/api/memory/list?keyword=海盐冰淇淋")
    print("5. List memories:", list_res.status_code, len(list_res.json()["memories"]))
    assert list_res.status_code == 200
    assert any(m["id"] == mem_id for m in list_res.json()["memories"])

    # 6. Update Memory
    update_res = session.post(f"{BASE_URL}/api/memory/update", json={
        "id": mem_id,
        "content": "[测试/诊断] 哥哥今天带音理去吃了海盐冰淇淋和草莓蛋糕，非常美味。",
        "mem_type": "episode",
        "importance": 5.0,
        "user_id": "10001"
    })
    print("6. Update memory:", update_res.status_code, update_res.json())
    assert update_res.status_code == 200

    # 7. Simulate Retrieval
    sim_res = session.post(f"{BASE_URL}/api/memory/simulate", json={
        "query": "海盐冰淇淋好吃吗",
        "user_id": "10001",
        "top_k": 3,
        "alpha": 0.7,
        "decay_rate": 0.1
    })
    print("7. Simulate retrieval:", sim_res.status_code, sim_res.json()["count"], "results")
    assert sim_res.status_code == 200
    assert sim_res.json()["count"] > 0

    # 8. Graph Data
    graph_res = session.get(f"{BASE_URL}/api/memory/graph?limit=50")
    print("8. Graph data:", graph_res.status_code, "nodes:", len(graph_res.json()["nodes"]), "links:", len(graph_res.json()["links"]))
    assert graph_res.status_code == 200
    assert len(graph_res.json()["nodes"]) > 0

    # 9. Soft Delete & Restore
    del_res = session.post(f"{BASE_URL}/api/memory/delete", json={"id": mem_id, "hard": False})
    print("9. Soft delete:", del_res.status_code, del_res.json())
    assert del_res.status_code == 200

    restore_res = session.post(f"{BASE_URL}/api/memory/restore/{mem_id}")
    print("10. Restore memory:", restore_res.status_code, restore_res.json())
    assert restore_res.status_code == 200

    # 10. Forget Maintenance
    forget_res = session.post(f"{BASE_URL}/api/memory/maintenance/forget")
    print("11. Forget maintenance:", forget_res.status_code, forget_res.json())
    assert forget_res.status_code == 200

    # 11. Clear Test Memories
    clear_res = session.post(f"{BASE_URL}/api/memory/maintenance/clear_test")
    print("12. Clear test memories:", clear_res.status_code, clear_res.json())
    assert clear_res.status_code == 200

    print("ALL MEMORY API TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_memory_flow()
