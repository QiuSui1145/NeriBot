import os
import requests
import io
import zipfile
import json
import csv

BASE_URL = "http://127.0.0.1:8088"
session = requests.Session()

def test_features():
    print("=== 开始端到端自动化测试 ===")

    # 1. 登录
    admin_pw = "admin"
    if os.path.exists("config/config.json"):
        try:
            with open("config/config.json", "r", encoding="utf-8") as f:
                admin_pw = json.load(f).get("security", {}).get("admin_password", "admin")
        except Exception:
            pass
    login_res = session.post(f"{BASE_URL}/api/auth/login", json={"username": "admin", "password": admin_pw})
    assert login_res.status_code == 200, f"登录失败: {login_res.text}"
    print("1. [PASS] 管理员登录成功")

    # 2. 测试出厂初始化接口 POST /api/memory/reset_factory
    reset_res = session.post(f"{BASE_URL}/api/memory/reset_factory")
    assert reset_res.status_code == 200, f"出厂初始化失败: {reset_res.text}"
    reset_data = reset_res.json()
    print("2. [PASS] 出厂初始化响应:", reset_data)
    assert reset_data["status"] == "ok"
    assert reset_data["inserted"] >= 8

    # 3. 验证记忆统计状态 GET /api/memory/stats
    stats_res = session.get(f"{BASE_URL}/api/memory/stats")
    assert stats_res.status_code == 200
    stats = stats_res.json()["stats"]
    print(f"3. [PASS] 状态验证: 健康={stats['healthy']}, 总数={stats['total_count']}, 维度={stats['dimension']}")
    assert stats["healthy"] is True
    assert stats["dimension"] == 512
    assert stats["total_count"] >= 8
    assert stats["fact_count"] >= 5
    assert stats["episode_count"] >= 3

    # 4. 验证记忆列表 GET /api/memory/list
    list_res = session.get(f"{BASE_URL}/api/memory/list")
    assert list_res.status_code == 200
    mems = list_res.json()["memories"]
    print(f"4. [PASS] 列表验证: 成功获取 {len(mems)} 条记忆碎片")
    assert any("钟城晓" in m["content"] for m in mems)
    assert any("风又音理" in m["content"] for m in mems)

    # 5. 验证记忆库导出 ZIP 接口 GET /api/memory/export
    export_res = session.get(f"{BASE_URL}/api/memory/export")
    assert export_res.status_code == 200, f"导出失败: {export_res.text}"
    content_disp = export_res.headers.get("Content-Disposition", "")
    print(f"5. [PASS] 导出接口响应成功, Content-Disposition: {content_disp}")
    assert ".zip" in content_disp.lower()

    # 解包并验证 ZIP 归档包内容
    zip_buf = io.BytesIO(export_res.content)
    with zipfile.ZipFile(zip_buf, "r") as zf:
        namelist = zf.namelist()
        print("   ZIP 包含文件列表:", namelist)
        assert "memories.json" in namelist
        assert "memories.csv" in namelist
        assert "metadata.json" in namelist
        assert "README.txt" in namelist

        # 验证 memories.json
        json_bytes = zf.read("memories.json")
        json_items = json.loads(json_bytes.decode("utf-8"))
        assert len(json_items) >= 8
        print(f"   [PASS] memories.json 解析成功: 共 {len(json_items)} 条记录")

        # 验证 memories.csv (UTF-8 BOM)
        csv_bytes = zf.read("memories.csv")
        assert csv_bytes.startswith(b"\xef\xbb\xbf"), "CSV 应带有 UTF-8 BOM"
        csv_text = csv_bytes.decode("utf-8-sig")
        csv_rows = list(csv.reader(io.StringIO(csv_text)))
        print(f"   [PASS] memories.csv 解析成功: 表头={csv_rows[0]}, 行数={len(csv_rows)}")
        assert csv_rows[0] == ["ID", "用户ID", "记忆内容", "类型", "重要度", "已遗忘归档", "访问次数", "创建时间", "最后访问时间"]

        # 验证 metadata.json
        meta_dict = json.loads(zf.read("metadata.json").decode("utf-8"))
        assert meta_dict["archive_type"] == "neri_memories_backup"
        assert meta_dict["total_count"] >= 8
        print(f"   [PASS] metadata.json 验证通过")

    # 6. 验证 TTS 权重切换与配置保存接口 POST /api/tts/service/switch_weights
    test_gpt = r"D:\GPT-SoVITS\GPT-SoVITS-v2pro-20250604\GPT_weights_v4\inori_v4-e15.ckpt"
    test_sovits = r"D:\GPT-SoVITS\GPT-SoVITS-v2pro-20250604\SoVITS_weights_v4\inori_v4_e15_s1740_l32.pth"
    switch_res = session.post(f"{BASE_URL}/api/tts/service/switch_weights", json={
        "gpt_weights_path": test_gpt,
        "sovits_weights_path": test_sovits
    })
    assert switch_res.status_code == 200, f"TTS 权重切换失败: {switch_res.text}"
    switch_data = switch_res.json()
    print("6. [PASS] TTS 权重切换结果:", switch_data)
    assert switch_data["status"] == "success"
    assert switch_data["gpt_weights_path"] == test_gpt
    assert switch_data["sovits_weights_path"] == test_sovits

    # 7. 验证全局配置读取包含新权重字段 GET /api/config
    cfg_res = session.get(f"{BASE_URL}/api/config")
    assert cfg_res.status_code == 200
    tts_cfg = cfg_res.json()["tts"]
    print("7. [PASS] 全局 TTS 配置读取验证:", tts_cfg.get("gpt_weights_path"), tts_cfg.get("sovits_weights_path"))
    assert tts_cfg["gpt_weights_path"] == test_gpt
    assert tts_cfg["sovits_weights_path"] == test_sovits

    print("=== 全部测试 100% 验证通过！===")

if __name__ == "__main__":
    test_features()
