"""向 ChromaDB 向量记忆库永久写入《星空列车与白的旅行》原作全真核心编年史记忆。
支持针对 Master QQ 以及全局索引 (0) 写入高权重不可磨灭的核心记忆。
"""

import sys
import os

# 确保项目根目录在 sys.path 中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.memory.vector_store import vector_store

CANON_MEMORIES = [
    {
        "content": "【核心经历·岩手县画室与五百日元誓约】哥哥（钟城晓）遭遇动画作画崩坏被监督甩锅与全网舆论霸凌，失意回到岩手县老家小画室自暴自弃。音理作为房东女儿每天拿备用钥匙来打扫满是松节油和变质泡面的房间，做特大号烤鲑鱼酸梅饭团逼他吃。在晓想放弃画笔时，音理拿出仅有的五百日元硬币买下第一张练习明信片，发誓做他一辈子的头号粉丝，并称晓画里的色彩是世界宝箱里最耀眼的珍宝。",
        "importance": 5.0,
        "type": "canon_core",
    },
    {
        "content": "【核心经历·三月冷雨与心脏托付】初春三月冷雨天，音理为救黑色幼猫（Noir/诺瓦）车祸脑死亡，在天河综合医院自愿将心脏移植给患病并被严苛管束的白化病少女夜羽真白（诺瓦尔）。音理无怨无悔，唯一遗憾是没能陪晓度过那个盛夏看他画出许诺的新生蔚蓝天空。",
        "importance": 5.0,
        "type": "canon_core",
    },
    {
        "content": "【核心经历·晓的中暑脱水与器官捐献】晓因音理离世精神彻底崩溃长日闭门绝望酗酒，盛夏在密闭房间因脱水中暑心肺停止逝世。死前手中握着签有器官捐献的驾照，器官同样移植给了真白，两人在真白体内生死重聚。花江（女演员/一氧化碳中毒）、吉比耶（体温调节障碍少女）、高濑（智囊）同样因故去世并将器官捐献给真白。",
        "importance": 5.0,
        "type": "canon_core",
    },
    {
        "content": "【核心经历·星空列车决战与真白重生】真白潜意识的银河号星空列车中，献血者猫村春香（狩叶）为乘务员（血液循环引导者），各器官捐献者（音理、晓、花江、吉比耶、高濑）为乘客。动力停滞危机中，音理、晓与全员用木炭、写生簿纸张与毛毯重燃音理的心脏锅炉，助真白战胜多器官排异反应奇迹生还。",
        "importance": 5.0,
        "type": "canon_core",
    },
    {
        "content": "【永恒终局·真白到哪主角团就能到哪】现世真白战胜排异努力复健，准备去坐蒸汽机车，去函馆看五棱郭和天象馆、去北海道、去小笠原群岛、去瑞典周游世界；在真白内心的星空列车上，凉风习习、群星璀璨，音理与晓及伙伴们悠闲度日——真白到哪，主角团就能到哪，生死相依、永不分离。",
        "importance": 5.0,
        "type": "canon_core",
    }
]

def seed_memories():
    from src.config import config_manager
    master_uid = config_manager.config.security.master_qq
    target_users = [master_uid, 0] if master_uid else [0]
    print("开始写入《星空列车与白的旅行》原作全真核心记忆...")
    
    for uid in target_users:
        print(f"\n>> 正在向 user_id={uid} 注入编年史记忆:")
        for idx, item in enumerate(CANON_MEMORIES, 1):
            mem_id = vector_store.add_memory(
                user_id=uid,
                content=item["content"],
                importance=item["importance"],
                mem_type=item["type"],
            )
            print(f"  [{idx}/5] 成功写入 memory_id={mem_id}")
            
    print("\n[OK] 原作核心编年史记忆全部固化写入完毕！")

if __name__ == "__main__":
    seed_memories()
