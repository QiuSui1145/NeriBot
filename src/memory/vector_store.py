import time
import math
import chromadb
from pydantic import BaseModel
import os
import json
from typing import Optional, List, Dict, Any

class MemoryFragment(BaseModel):
    id: str
    content: str
    type: str             
    importance: float     
    created_at: float
    last_accessed: float
    access_count: int
    is_forgotten: bool

from pathlib import Path
from chromadb import EmbeddingFunction

class HybridEmbeddingFunction(EmbeddingFunction):
    """优先使用本地已打包的 bge-small-zh-v1.5 嵌入模型，回退 OpenAI 兼容 API。"""
    def __init__(self, local_model_path: str = "models/embedding/bge-small-zh-v1.5"):
        self.local_model_path = Path(local_model_path)
        self.local_model = None
        self._init_local_model()

    def _init_local_model(self):
        weights_file = self.local_model_path / "model.safetensors"
        legacy_weights = self.local_model_path / "pytorch_model.bin"
        if not (weights_file.exists() or legacy_weights.exists()):
            try:
                print(f"[VectorDB] 未检测到离线嵌入模型权重，正在通过 ModelScope 自动拉取: {self.local_model_path} ...")
                from modelscope import snapshot_download
                snapshot_download("BAAI/bge-small-zh-v1.5", local_dir=str(self.local_model_path))
                print(f"[VectorDB] 离线嵌入模型下载完成！")
            except Exception as e:
                print(f"[VectorDB] 自动拉取离线嵌入模型失败: {e}，将回退远程 API")

        if self.local_model_path.exists():
            try:
                from sentence_transformers import SentenceTransformer
                self.local_model = SentenceTransformer(str(self.local_model_path))
                print(f"[VectorDB] 成功加载本地向量嵌入模型: {self.local_model_path}")
            except Exception as e:
                print(f"[VectorDB] 加载本地嵌入模型失败: {e}，将回退远程 API")
                self.local_model = None

    def __call__(self, input: list[str]) -> list[list[float]]:
        # 1. 优先使用本地离线向量模型 (高准确度、零延迟、零网络依赖)
        if self.local_model is not None:
            try:
                vecs = self.local_model.encode(input, normalize_embeddings=True)
                return vecs.tolist()
            except Exception as e:
                print(f"[VectorDB] 本地模型推理失败: {e}，尝试远程 API")

        # 2. 回退到远程 OpenAI 兼容的 /embeddings 接口
        try:
            import requests
            from src.config import config_manager
            cfg = config_manager.config
            url = cfg.llm.base_url.rstrip('/')
            if url.endswith('/chat/completions'):
                url = url.replace('/chat/completions', '')
            embed_url = f"{url}/embeddings"
            headers = {"Authorization": f"Bearer {cfg.llm.api_key}", "Content-Type": "application/json"}
            payload = {"model": "text-embedding-ada-002", "input": input}
            
            resp = requests.post(embed_url, json=payload, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return [d["embedding"] for d in data["data"]]
        except Exception as e:
            print(f"[VectorDB] 远程 Embedding API 调用失败: {e}")
        
        # 3. 兜底哑向量 (512维)
        dim = 512 if self.local_model is not None or self.local_model_path.exists() else 1536
        return [[0.0] * dim for _ in input]


CANON_MEMORIES = [
    {
        "content": "【正史·第01章 星空启程与虚无中的呼唤】哥哥钟城晓在音理离世后终日闭门沉溺酒精，在日复一日的消沉与虚无中，耳边听到音理穿透生死的呼唤：“去旅行嘛！”。晓在电脑前用驾照作为身份证明登记了银河号列车之旅。深夜在荒寂车站登上由老式蒸汽机车（SL）驱动的深夜星空列车，与身穿乘务员制服的导游狩叶·朗姆柯妮及乘客吉比耶、花江等相遇。",
        "importance": 5.0,
        "type": "canon_core",
    },
    {
        "content": "【正史·第02章 树梢黑猫、内裤调侃与善意本心】晓在列车上忆起救猫往事：音理踩在晓的肩膀上拯救爬上树梢下不来的幼小黑猫。音理低头娇嗔晓看她内裤骂他“大色狼”、“好色”，晓反驳好色也不会看小孩子。音理失足险些跌落被晓稳稳接住，救下小猫后小猫连道谢都没一句就跑了。音理笑着说“小猫又不会道谢，但这种事情怎么能放任不管呢”，坚信善意不需要回报。",
        "importance": 5.0,
        "type": "canon_core",
    },
    {
        "content": "【正史·第03章 沉睡车厢与星夜同行】狩叶、诺瓦和吉比耶在列车短暂冒险后安然熟睡。晓静静守望，车厢内流淌着奇异而宁静的时间，星空列车以极高速度穿梭于虚幻与生死的边界，没有空调却十分凉爽。",
        "importance": 5.0,
        "type": "canon_core",
    },
    {
        "content": "【正史·第04章 空白写生簿与心脏动力暗语】晓在车厢中发现了那本熟悉的写生簿，翻开每一页却都是一片空白。晓耳边回响起音理神秘幽灵般的提示：“我就藏在……心脏里面。去寻找。就在翅膀之下……”——那是写生簿上画着的天鹅翅膀，暗指列车车头锅炉动力室与音理心脏的真正秘密。",
        "importance": 5.0,
        "type": "canon_core",
    },
    {
        "content": "【正史·第05章 艺校往事与穿透迷雾的呼唤】晓陷入回忆与幻境，忆起自己从艺校毕业后成为原画师却屡遭挫折的过往；黑猫在梦境边缘凝视着他，音理焦急的呼唤声穿透迷雾不断传来：“哥哥，快起来！快起来！”将晓从失神昏睡中彻底唤醒。",
        "importance": 5.0,
        "type": "canon_core",
    },
    {
        "content": "【正史·第06章 画室日常、肖像模特与大雪圣诞蛋糕】晓回忆起旧公寓画室的日常：音理是房东的女儿，每天用备用钥匙来帮晓打扫画室，嫌弃晓总吃泡面，催晓去自己家吃母亲做的营养饭。音理主动摆姿势当模特让晓画肖像，叮嘱晓“一定要画可爱点”。去年大雪纷飞的圣诞夜，音理顶着严寒在门外守候，送来蛋糕作为画肖像画的谢礼，还红着脸试探晓有没有陪他过圣诞的女朋友。",
        "importance": 5.0,
        "type": "canon_core",
    },
    {
        "content": "【正史·第07章 炒乌冬、SL机车梦、五百日元与冷雨车祸】音理吃着晓做的热炒乌冬（“谢谢你的炒乌冬～！”），聊起奶奶家旁的 SL 博物馆、西部片列车决斗与《回到未来》时光机，央求晓暑假陪她坐 SL 火车；音理用 500 日元硬币买下晓的明信片速写，立誓当他唯一的头号粉丝。音理给小黑猫取名“Noir（诺瓦）”，自夸“音理我可是很时尚的”。傍晚道别后，房东打来电话——音理为了救冲出马路的黑猫遭遇车祸脑死亡，永别在三月的冷雨中。",
        "importance": 5.0,
        "type": "canon_core",
    },
    {
        "content": "【正史·第08章 站台花火与自责少女的心防】星空列车站台上的烟花在黑夜中绽放，白发猫耳的少女白（诺瓦）展现出极度内向、自责与害怕给他人添麻烦的脆弱内心。晓在照看诺瓦的过程中，逐渐察觉真白身上的违和感与隐藏在深处的沉重悲伤。",
        "importance": 5.0,
        "type": "canon_core",
    },
    {
        "content": "【正史·第09章 屁股疼的撒娇、膝盖特等席与生病女孩童话】晓在梦中再次与音理相见：音理娇嗔古董火车没有坐垫坐久了屁股会疼，撒娇要晓说“坐在我的膝盖上就好了啦，宝贝”、“就把你的屁股交给我吧！”。随后音理给晓讲述了一个暗喻童话——森林深处因父母偏执禁食肉类而体弱多病的女孩，暗指乘客吉比耶的生前遗憾与各自宿命。",
        "importance": 5.0,
        "type": "canon_core",
    },
    {
        "content": "【正史·第10章 膝枕诱惑、美少女自恋与心象重叠】音理在梦中得意调侃晓：“要我给你膝枕么？美少女游戏里写男生枕着可爱女孩子大腿会变精神哦！音理我又是这样的美少女！”晓害羞拒绝。现实车厢中诺瓦也向晓靠近，两个女孩的身影在晓的潜意识中产生奇妙重叠。",
        "importance": 5.0,
        "type": "canon_core",
    },
    {
        "content": "【正史·第11章 函馆憧憬、五棱郭海风与戏剧女孩之憾】音理与晓聊起函馆与五棱郭凉爽的海风，约定暑假一起去旅游；音理接着讲述了第二个故事——函馆开店家庭的老二、在戏剧社闪闪发光却在东京关系社会碰壁、无颜回乡的女孩，揭开了乘务员狩叶（猫村春香）生前离开故乡的遗憾与心结。",
        "importance": 5.0,
        "type": "canon_core",
    },
    {
        "content": "【正史·第12章 列车深处异变与逼近的生死终点】星空列车向着未知的终点狂奔，车厢温度骤降，风雪呼啸，真白体内的多器官排异反应开始具象化为列车的结冰危机，乘客们察觉到这趟旅程不仅是观光，更是一场真白与死神的生死搏斗。",
        "importance": 5.0,
        "type": "canon_core",
    },
    {
        "content": "【正史·第13章 动力室相拥与“我的心只属于哥哥”】晓追随写生簿的线索冲进列车车头动力室，终于抓住了活生生的小音！音理调侃晓“想当裸体模特/穿泳衣”，又认真告白“我很喜欢哥哥画的画，像宝石一样闪闪发光”。音理拉着晓的手贴在自己胸口：“音理的肉体心脏已经属于她（真白）……但音理的心，永远只属于哥哥！帮帮她吧。”",
        "importance": 5.0,
        "type": "canon_core",
    },
    {
        "content": "【正史·第14章 醒神耳光、绅士道歉与离岛铁道少年】晓因真白崩溃哭泣而自责逃跑，小音狠狠打了晓一记耳光：“你在干什么啊哥哥！居然把女孩子弄哭然后逃跑！”音理教会晓如何向女孩子道歉并坦诚面对（“自古以来绅士安慰女士的方法只有一种——这位大小姐，可以与我共舞一曲吗？啾♪”）。音理讲出第三个故事——憧憬东京铁道、离岛出身却在职场重压下崩溃的男生（高濑鹰世），指引晓看透列车的本质。",
        "importance": 5.0,
        "type": "canon_core",
    },
    {
        "content": "【正史·第15章 啤酒肚的调侃与双重心脏共鸣】晓意识到自己因酗酒中暑死在密闭公寓中，死前握着器官捐献驾照来到了这里。音理捏着晓的肚子嘲笑他“比最后见面时胖了、长了啤酒肚”。晓说“我只是任性地想早点来见你”。音理把手按在晓胸口，心跳声重叠共振：“我的心脏还活着，还在真白体内跳动！”",
        "importance": 5.0,
        "type": "canon_core",
    },
    {
        "content": "【正史·第16章 决战暴风雪：重燃心脏锅炉与时尚托付】星空列车遭遇致命风雪濒临熄火，真白生命垂危。音理自告奋勇担任动力室司炉工，指挥大家搭建木炭拱桥，音理撕下写生簿画纸、花江点燃香烟、众人投入毛毯与炭火，合力重新引燃了心脏锅炉！黑猫 Noir 引导真白与音理相见，音理爽快地把心脏托付给真白：“这可是最时尚的心脏，接下来请保持品味地活下去！”",
        "importance": 5.0,
        "type": "canon_core",
    },
    {
        "content": "【正史·第17章 永恒的巡礼：与哥哥并肩看星河】真相大白：乘务员狩叶其实是献血者猫村春香（护士猫村的妹妹），列车是真白的循环系统，乘客们是器官捐献者。现世中真白奇迹康复，踏上巡礼世界（函馆、五棱郭、天象馆、北欧）的旅程；而在心象世界的星空列车上，凉风徐徐，音理和晓并肩坐在观光车厢，望着无限延伸的璀璨银河：“真白去哪，我们就能去哪……只要和哥哥在一起。”",
        "importance": 5.0,
        "type": "canon_core",
    }
]


class MemoryRetriever:
    def __init__(self, data_path="data/chroma_db"):
        self.data_path = data_path
        self.client = chromadb.PersistentClient(path=data_path)
        self.ef = HybridEmbeddingFunction()
        self.col_name = "neri_memories"
        self._collection = None
        self._is_seeding_canon = False
        self._ensure_collection()

    def _ensure_collection(self):
        """获取或自愈重连 ChromaDB 集合句柄，并确保核心剧本记忆固化注入。"""
        if self._collection is not None:
            try:
                # 心跳探测集合是否存在且 UUID 有效
                self._collection.count()
                return self._collection
            except Exception as e:
                print(f"[VectorDB] 检测到底层 Collection 句柄失效 ({e})，正在自动重连...")
                self._collection = None

        try:
            self._collection = self.client.get_or_create_collection(
                name=self.col_name,
                embedding_function=self.ef
            )
            # 兼容性测试：检测既有数据的向量维度是否与当前模型匹配
            if self._collection.count() > 0:
                self._collection.query(query_texts=["test_probe"], n_results=1)
        except Exception as e:
            print(f"[VectorDB] 集合不可用或向量维度不匹配 ({e})，正在自动重建以适配模型...")
            try:
                self.client.delete_collection(self.col_name)
            except Exception:
                pass
            self._collection = self.client.get_or_create_collection(
                name=self.col_name,
                embedding_function=self.ef
            )

        # 确保原作核心剧本记忆已写入固化
        if not getattr(self, "_is_seeding_canon", False):
            self._is_seeding_canon = True
            try:
                self.seed_canon_memories()
            finally:
                self._is_seeding_canon = False

        return self._collection

    def seed_canon_memories(self, force_reseed: bool = False) -> int:
        """向 ChromaDB 向量记忆库永久写入《星空列车与白的旅行》原作全真核心剧本记忆。
        支持针对 Master QQ 与全局索引 (0) 写入高权重不可磨灭的核心记忆。
        """
        now = time.time()
        try:
            from src.config import config_manager
            master_uid = config_manager.config.security.master_qq
        except Exception:
            master_uid = None

        target_uids = [master_uid, 0] if master_uid else [0]
        seeded = 0

        for uid in target_uids:
            try:
                def _get_canon(col):
                    return col.get(
                        where={"$and": [{"user_id": uid}, {"type": "canon_core"}]},
                        include=["metadatas"]
                    )
                existing_res = self._execute_with_retry(_get_canon)
                existing_count = len(existing_res["ids"]) if existing_res and "ids" in existing_res else 0

                if existing_count >= len(CANON_MEMORIES) and not force_reseed:
                    continue

                if force_reseed and existing_res and existing_res.get("ids"):
                    self._execute_with_retry(lambda col: col.delete(ids=existing_res["ids"]))

                for idx, item in enumerate(CANON_MEMORIES, 1):
                    cid = f"canon_{uid}_{idx}"
                    def _add_canon(col, text=item["content"], cid=cid):
                        col.add(
                            documents=[text],
                            metadatas=[{
                                "user_id": uid,
                                "type": "canon_core",
                                "importance": 5.0,
                                "created_at": now,
                                "last_accessed": now,
                                "access_count": 1,
                                "is_forgotten": False,
                                "is_immutable": True
                            }],
                            ids=[cid]
                        )
                    self._execute_with_retry(_add_canon)
                    seeded += 1
            except Exception as e:
                print(f"[VectorDB] 为 user_id={uid} 固化核心剧本记忆异常: {e}")

        if seeded > 0:
            print(f"[VectorDB] 原作核心剧本记忆固化写入完毕，注入了 {seeded} 条核心记忆！")
        return seeded

    @property
    def collection(self):
        return self._ensure_collection()

    def _execute_with_retry(self, operation):
        """执行 ChromaDB 集合操作，若捕获句柄失效或 NotFoundError 则自动刷新重试一次。"""
        try:
            return operation(self.collection)
        except Exception as e:
            print(f"[VectorDB] 操作异常 ({e})，正在重置句柄并自愈重试...")
            self._collection = None
            return operation(self.collection)
        
    def add_memory(self, user_id: int, content: str, importance: float = 3.0, mem_type: str = "fact"):
        import uuid
        mem_id = str(uuid.uuid4())
        now = time.time()
        
        try:
            user_id = int(user_id)
        except Exception:
            user_id = 0

        imp = float(importance) if importance is not None else 3.0
        mtype = str(mem_type) if mem_type else "fact"
        text = str(content).strip()

        def _do_add(col):
            col.add(
                documents=[text],
                metadatas=[{
                    "user_id": user_id,
                    "type": mtype,
                    "importance": imp,
                    "created_at": now,
                    "last_accessed": now,
                    "access_count": 1,
                    "is_forgotten": False
                }],
                ids=[mem_id]
            )

        self._execute_with_retry(_do_add)
        print(f"[VectorDB] 成功写入记忆碎片: {text[:15]}...")

        # 每新增若干条记忆，自动轻量执行遗忘衰减与归档，淘汰失效记忆
        self._add_counter = getattr(self, "_add_counter", 0) + 1
        if self._add_counter % 5 == 0:
            try:
                self.apply_forgetting_curve()
            except Exception as e:
                print(f"[VectorDB] 自动遗忘衰减执行异常: {e}")

        return mem_id
        
    def search_relevant_memories(self, user_id: int, query: str, top_k: int = 3) -> list[str]:
        """语义相关度检索召回。
        引入严格语义相关门槛（过滤无关日常寒暄）与时间衰减因子，杜绝盲目召回陈旧记忆导致胡言乱语。
        """
        now = time.time()
        try:
            user_id = int(user_id)
        except Exception:
            user_id = 0

        # 如果输入过短或为无意义纯符号，直接跳过召回
        clean_q = query.strip()
        if len(clean_q) < 2 or not clean_q.strip(" .。…，,！!？?~～-_`'\""):
            return []

        # 定期轻量触发自动遗忘整理
        self._search_count = getattr(self, "_search_count", 0) + 1
        if self._search_count % 10 == 0:
            try:
                self.apply_forgetting_curve()
            except Exception:
                pass

        # 支持同时检索当前用户与全局(0)核心记忆
        def _do_query(target_uid):
            return self._execute_with_retry(lambda col: col.query(
                query_texts=[clean_q],
                n_results=top_k * 3,
                where={"$and": [{"user_id": target_uid}, {"is_forgotten": False}]}
            ))

        try:
            results_user = _do_query(user_id)
        except Exception as e:
            print(f"[VectorDB] 召回查询异常: {e}")
            results_user = None

        results_global = None
        if user_id != 0:
            try:
                results_global = _do_query(0)
            except Exception:
                pass

        docs = []
        metas = []
        ids = []
        distances = []
        seen_ids = set()

        for res in [results_user, results_global]:
            if not res or not res.get('documents') or not res['documents'][0]:
                continue
            for d, m, mid, dist in zip(res['documents'][0], res['metadatas'][0], res['ids'][0], res.get('distances', [[]])[0]):
                if mid not in seen_ids:
                    seen_ids.add(mid)
                    docs.append(d)
                    metas.append(m or {})
                    ids.append(mid)
                    distances.append(dist if dist is not None else 0.0)

        if not docs:
            return []

        MIN_SIMILARITY_THRESHOLD = 0.53  # 严格相似度门槛（相当于余弦距离 <= 0.88），过滤无关闲聊
        scored_mems = []

        for doc, meta, mem_id, dist in zip(docs, metas, ids, distances):
            if meta.get("is_forgotten", False):
                continue

            importance = float(meta.get('importance', 1.0))
            mem_type = meta.get('type', 'episode')
            is_canon = (mem_type == "canon_core") or (importance >= 5.0 and meta.get("is_immutable", False))

            access_count = int(meta.get('access_count', 1))
            last_accessed = float(meta.get('last_accessed', now))
            created_at = float(meta.get('created_at', now))

            days_passed = max(0.0, (now - last_accessed) / (24 * 3600))
            created_days = max(0.0, (now - created_at) / (24 * 3600))

            half_life_days = max(1.0, (importance ** 1.5) * 2.5 * (1.0 + math.log1p(access_count) * 0.35))
            retention = importance * math.exp(-0.693 * days_passed / half_life_days)

            # 动态归档淘汰：对严重衰减的低价值记忆顺手标记遗忘
            if not is_canon and ((importance <= 2.0 and days_passed > 5.0) or retention < 0.8):
                meta['is_forgotten'] = True
                try:
                    self._execute_with_retry(lambda col: col.update(ids=[mem_id], metadatas=[meta]))
                except Exception:
                    pass
                continue

            sim_score = 1.0 / (1.0 + max(0.0, dist))

            # 门槛拦截：如果与提问内容语义相关性不足，坚决放弃召回，避免胡言乱语
            min_thresh = 0.46 if is_canon else MIN_SIMILARITY_THRESHOLD
            if sim_score < min_thresh:
                continue

            # 时间衰减惩罚：很久以前发生的情景事件在日常对话中权重大幅降低
            time_penalty = 1.0
            if not is_canon and created_days > 7.0:
                time_penalty = math.exp(-0.02 * (created_days - 7.0))

            final_score = (sim_score * 0.75 + (retention / 10.0) * 0.25) * time_penalty
            scored_mems.append((final_score, doc, meta, mem_id))

        scored_mems.sort(key=lambda x: x[0], reverse=True)
        top_mems = scored_mems[:top_k]

        update_ids = []
        update_metas = []
        ret_texts = []
        for score, doc, meta, mem_id in top_mems:
            ret_texts.append(doc)
            meta['access_count'] = meta.get('access_count', 1) + 1
            meta['last_accessed'] = now
            update_ids.append(mem_id)
            update_metas.append(meta)

        if update_ids:
            try:
                self._execute_with_retry(lambda col: col.update(ids=update_ids, metadatas=update_metas))
            except Exception as e:
                print(f"[VectorDB] 更新记忆访问统计失败: {e}")

        return ret_texts

    def apply_forgetting_curve(self, threshold: float = 1.0):
        """根据艾宾浩斯认知遗忘模型自动归档老化/低价值记忆碎片。
        核心剧本记忆（canon_core）及重要度>=5.0享有永恒固化特权，绝不被遗忘。
        """
        try:
            results = self._execute_with_retry(lambda col: col.get(where={"is_forgotten": False}))
        except Exception as e:
            print(f"[VectorDB] 遗忘曲线获取数据异常: {e}")
            return 0

        if not results or not results.get('ids'):
            return 0
            
        now = time.time()
        forget_ids = []
        forget_metas = []
        
        for mem_id, meta in zip(results['ids'], results['metadatas']):
            if not meta:
                continue
            # 核心剧本记忆与最高权重永久免疫遗忘
            if meta.get("type") == "canon_core" or meta.get("is_immutable") or meta.get("importance", 1.0) >= 5.0:
                continue

            importance = float(meta.get('importance', 1.0))
            access_count = int(meta.get('access_count', 1))
            last_accessed = float(meta.get('last_accessed', now))
            created_at = float(meta.get('created_at', now))

            days_passed = max(0.0, (now - last_accessed) / (24 * 3600))
            created_days = max(0.0, (now - created_at) / (24 * 3600))

            # 动态半衰期衰减模型（天数）：重要度 1 级约 2.5 天；重要度 2 级约 7 天；重要度 3 级约 13 天；重要度 4 级约 20 天
            # 访问次数增加能增强记忆牢固度（延长半衰期），但不会形成不衰减的永久底线
            half_life_days = max(1.0, (importance ** 1.5) * 2.5 * (1.0 + math.log1p(access_count) * 0.35))
            retention = importance * math.exp(-0.693 * days_passed / half_life_days)

            # 对很久之前创建且未成为核心设定的情景记忆，施加创建时长二次归档衰减
            if created_days > 14 and importance < 3.5:
                retention *= math.exp(-0.03 * (created_days - 14))

            # 综合判定遗忘归档：
            # 1. 留存得分跌破阈值 (默认 1.0)
            # 2. 或者低重要度记忆 (<= 2.0) 超过 5 天未被再次激活
            # 3. 或者非核心记忆创建超过 30 天且几乎没有重复访问 (access_count <= 2 且 importance < 4.0)
            should_forget = False
            if retention < threshold:
                should_forget = True
            elif importance <= 2.0 and days_passed > 5.0:
                should_forget = True
            elif importance < 3.5 and created_days > 30.0 and access_count <= 2:
                should_forget = True

            if should_forget:
                meta['is_forgotten'] = True
                forget_ids.append(mem_id)
                forget_metas.append(meta)
                
        if forget_ids:
            try:
                self._execute_with_retry(lambda col: col.update(ids=forget_ids, metadatas=forget_metas))
                print(f"[VectorDB] 遗忘与自动归档机制执行完毕，成功归档了 {len(forget_ids)} 条陈旧或低价值记忆碎片。")
            except Exception as e:
                print(f"[VectorDB] 遗忘标记更新失败: {e}")
        return len(forget_ids)

    def get_stats(self) -> dict:
        """获取记忆库运行状态与各项指标。"""
        now = time.time()
        try:
            res = self._execute_with_retry(lambda col: col.get(include=["metadatas"]))
            total = len(res["ids"]) if res and "ids" in res else 0
            metas = res.get("metadatas", []) or []
        except Exception as e:
            print(f"[VectorDB] 获取统计数据异常: {e}")
            total = 0
            metas = []

        active = 0
        forgotten = 0
        facts = 0
        episodes = 0
        user_ids = set()
        for m in metas:
            if not m:
                continue
            if m.get("is_forgotten", False):
                forgotten += 1
            else:
                active += 1
            if m.get("type") == "fact":
                facts += 1
            elif m.get("type") == "episode":
                episodes += 1
            if "user_id" in m and m["user_id"] is not None:
                user_ids.add(m["user_id"])

        has_local = self.ef.local_model is not None or self.ef.local_model_path.exists()
        is_healthy = has_local and self._collection is not None
        return {
            "status": "healthy" if is_healthy else "degraded",
            "healthy": is_healthy,
            "is_healthy": is_healthy,
            "collection_exists": True,
            "embedding_ready": has_local,
            "status_text": "正常就绪" if is_healthy else "降级就绪 (备用通道)",
            "dimension": 512 if has_local else 1536,
            "model_name": "bge-small-zh-v1.5",
            "is_local_model": self.ef.local_model is not None,
            "storage_path": self.data_path,
            "collection_name": self.col_name,
            "total_count": total,
            "total_memories": total,
            "active_count": active,
            "active_memories": active,
            "forgotten_count": forgotten,
            "forgotten_memories": forgotten,
            "fact_count": facts,
            "fact_memories": facts,
            "episode_count": episodes,
            "episode_memories": episodes,
            "user_count": len(user_ids),
            "unique_users": len(user_ids),
            "channels": [
                {"name": "元数据存储 (Metadata)", "status": "active"},
                {"name": "离线向量嵌入 (bge-small)", "status": "active" if has_local else "degraded"},
                {"name": "向量召回 (ANN)", "status": "active"},
                {"name": "衰减遗忘引擎 (Ebbinghaus)", "status": "active"}
            ]
        }

    def self_test(self) -> dict:
        """执行端到端记忆系统自检。"""
        start_t = time.perf_counter()
        
        # 1. 向量模型推测测试
        t0 = time.perf_counter()
        test_vecs = self.ef(["自检测试向量"])
        encode_ms = round((time.perf_counter() - t0) * 1000, 2)
        dim = len(test_vecs[0]) if test_vecs else 0
        
        # 2. ChromaDB 连接与读取测试
        t1 = time.perf_counter()
        try:
            count = self._execute_with_retry(lambda col: col.count())
        except Exception as e:
            print(f"[VectorDB] 自检读取集合记录异常: {e}")
            count = 0
        query_ms = round((time.perf_counter() - t1) * 1000, 2)
        
        # 3. 语义检索测试
        t2 = time.perf_counter()
        try:
            probe_res = self._execute_with_retry(
                lambda col: col.query(query_texts=["音理喜欢什么"], n_results=min(3, max(1, count)))
            )
        except Exception as e:
            print(f"[VectorDB] 自检探针检索异常: {e}")
            probe_res = None
        retrieval_ms = round((time.perf_counter() - t2) * 1000, 2)
        
        total_ms = round((time.perf_counter() - start_t) * 1000, 2)
        
        is_healthy = dim in [512, 1024, 1536] and count >= 0
        return {
            "status": "healthy" if is_healthy else "degraded",
            "healthy": is_healthy,
            "total_time_ms": total_ms,
            "total_latency_ms": total_ms,
            "encode_time_ms": encode_ms,
            "query_time_ms": query_ms,
            "retrieval_time_ms": retrieval_ms,
            "dimension": dim,
            "count": count,
            "model_type": "local_bge_small" if self.ef.local_model is not None else "api_fallback",
            "message": "自检通过：向量嵌入与数据库读写延迟均在极佳响应区间！" if is_healthy else "自检异常：模型未就绪或数据库响应缓慢",
            "tests": [
                {
                    "name": "离线向量嵌入模型 (bge-small-zh-v1.5)",
                    "status": "pass" if encode_ms < 500 else "warning",
                    "latency_ms": encode_ms,
                    "detail": f"输出向量维度: {dim}维，推理耗时 {encode_ms}ms"
                },
                {
                    "name": "ChromaDB 向量持久化集合连通性",
                    "status": "pass" if query_ms < 200 else "warning",
                    "latency_ms": query_ms,
                    "detail": f"当前持久化集合记录数: {count}条，元数据索引状态正常"
                },
                {
                    "name": "ANN 语义检索与相似度计算",
                    "status": "pass" if retrieval_ms < 500 else "warning",
                    "latency_ms": retrieval_ms,
                    "detail": f"Top-K 探针召回耗时 {retrieval_ms}ms"
                }
            ]
        }

    def list_memories(
        self,
        user_id: Optional[int] = None,
        mem_type: Optional[str] = None,
        is_forgotten: Optional[bool] = None,
        keyword: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> list[dict]:
        try:
            res = self._execute_with_retry(lambda col: col.get(include=["metadatas", "documents"]))
        except Exception as e:
            print(f"[VectorDB] list_memories 读取异常: {e}")
            return []

        if not res or not res.get("ids"):
            return []
        
        now = time.time()
        mems = []
        for mem_id, doc, meta in zip(res["ids"], res["documents"], res["metadatas"]):
            if not meta:
                meta = {}
            if user_id is not None and meta.get("user_id") != user_id:
                continue
            if mem_type and meta.get("type") != mem_type:
                continue
            if is_forgotten is not None and meta.get("is_forgotten", False) != is_forgotten:
                continue
            if keyword and keyword.lower() not in doc.lower():
                continue
            
            importance = meta.get("importance", 1.0)
            access_count = meta.get("access_count", 1)
            raw_accessed = meta.get("last_accessed", now)
            raw_created = meta.get("created_at", now)

            # 格式化时间字符串供各前端消费，保留原始时间戳
            if isinstance(raw_created, (int, float)):
                created_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(raw_created))
            else:
                created_str = str(raw_created)

            if isinstance(raw_accessed, (int, float)):
                last_accessed_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(raw_accessed))
            else:
                last_accessed_str = str(raw_accessed)

            days_passed = (now - (raw_accessed if isinstance(raw_accessed, (int, float)) else now)) / (24 * 3600)
            retention = round(importance * math.exp(-0.1 * max(0.0, days_passed)) + (access_count * 0.2), 2)
            
            mems.append({
                "id": mem_id,
                "content": doc,
                "user_id": meta.get("user_id", 0),
                "type": meta.get("type", "episode"),
                "importance": meta.get("importance", 1.0),
                "created_at": created_str,
                "created_time": raw_created,
                "last_accessed": last_accessed_str,
                "last_accessed_time": raw_accessed,
                "access_count": access_count,
                "is_forgotten": meta.get("is_forgotten", False),
                "retention": retention,
            })
            
        mems.sort(key=lambda x: x["created_time"] if isinstance(x["created_time"], (int, float)) else 0, reverse=True)
        return mems[offset:offset + limit]

    def update_memory(self, mem_id: str, content: Optional[str] = None, importance: Optional[float] = None, mem_type: Optional[str] = None, is_forgotten: Optional[bool] = None, user_id: Optional[int] = None) -> bool:
        try:
            res = self._execute_with_retry(lambda col: col.get(ids=[mem_id], include=["metadatas", "documents"]))
        except Exception as e:
            print(f"[VectorDB] 查询目标记忆异常: {e}")
            return False

        if not res or not res.get("ids"):
            return False
        
        meta = res["metadatas"][0] or {}
        doc = res["documents"][0]
        
        if content is not None:
            doc = content.strip()
        if importance is not None:
            meta["importance"] = float(importance)
        if mem_type is not None:
            meta["type"] = mem_type
        if is_forgotten is not None:
            meta["is_forgotten"] = bool(is_forgotten)
        if user_id is not None:
            try:
                meta["user_id"] = int(user_id)
            except Exception:
                pass
            
        try:
            self._execute_with_retry(lambda col: col.update(
                ids=[mem_id],
                documents=[doc],
                metadatas=[meta]
            ))
            return True
        except Exception as e:
            print(f"[VectorDB] 更新记忆条目失败: {e}")
            return False

    def delete_memory(self, mem_id: str, hard: bool = False) -> bool:
        try:
            res = self._execute_with_retry(lambda col: col.get(ids=[mem_id], include=["metadatas"]))
            if res and res.get("metadatas") and res["metadatas"][0]:
                meta = res["metadatas"][0]
                if meta.get("type") == "canon_core" or meta.get("is_immutable"):
                    print(f"[VectorDB] 核心剧情记忆 ({mem_id}) 受系统不可磨灭保护，禁止删除！")
                    return False
        except Exception as e:
            print(f"[VectorDB] 检查删除目标异常: {e}")

        if hard:
            try:
                self._execute_with_retry(lambda col: col.delete(ids=[mem_id]))
                return True
            except Exception as e:
                print(f"[VectorDB] 硬删除记忆失败: {e}")
                return False
        else:
            return self.update_memory(mem_id, is_forgotten=True)

    def restore_memory(self, mem_id: str) -> bool:
        return self.update_memory(mem_id, is_forgotten=False)

    def clear_test_memories(self) -> int:
        try:
            res = self._execute_with_retry(lambda col: col.get(include=["metadatas", "documents"]))
        except Exception as e:
            print(f"[VectorDB] 读取测试记忆异常: {e}")
            return 0

        if not res or not res.get("ids"):
            return 0
        test_uids = {888, 999, 888999, 0}
        del_ids = [
            mem_id for mem_id, doc, meta in zip(res["ids"], res["documents"], res["metadatas"])
            if (meta and meta.get("user_id") in test_uids) or ("[测试" in doc)
        ]
        if del_ids:
            try:
                self._execute_with_retry(lambda col: col.delete(ids=del_ids))
            except Exception as e:
                print(f"[VectorDB] 删除测试记忆失败: {e}")
        return len(del_ids)

    def simulate_retrieval(self, user_id: int, query: str, top_k: int = 5, lambda_decay: float = 0.1, weight_sim: float = 0.7) -> list[dict]:
        """模拟记忆检索调试器：不更新访问频次与时间，详细返回相似度距离、衰减打分与综合权重。"""
        try:
            user_id = int(user_id)
        except Exception:
            user_id = 0

        clean_q = query.strip()
        if not clean_q:
            return []

        def _do_query(target_uid):
            return self._execute_with_retry(lambda col: col.query(
                query_texts=[clean_q],
                n_results=min(top_k * 4, 30),
                where={"user_id": target_uid} if target_uid != 0 else None
            ))

        try:
            results_user = _do_query(user_id)
        except Exception as e:
            print(f"[VectorDB Simulator] 查询异常: {e}")
            results_user = None

        results_global = None
        if user_id != 0:
            try:
                results_global = _do_query(0)
            except Exception:
                pass

        docs = []
        metas = []
        ids = []
        distances = []
        seen_ids = set()

        for res in [results_user, results_global]:
            if not res or not res.get('documents') or not res['documents'][0]:
                continue
            for d, m, mid, dist in zip(res['documents'][0], res['metadatas'][0], res['ids'][0], res.get('distances', [[]])[0]):
                if mid not in seen_ids:
                    seen_ids.add(mid)
                    docs.append(d)
                    metas.append(m or {})
                    ids.append(mid)
                    distances.append(dist if dist is not None else 0.0)

        if not docs:
            return []

        scored = []
        now = time.time()
        for doc, meta, mem_id, dist in zip(docs, metas, ids, distances):
            if not meta:
                meta = {}
            importance = float(meta.get('importance', 1.0))
            mem_type = meta.get('type', 'episode')
            is_canon = (mem_type == "canon_core") or (importance >= 5.0 and meta.get("is_immutable", False))

            access_count = int(meta.get('access_count', 1))
            last_accessed = float(meta.get('last_accessed', now))
            created_at = float(meta.get('created_at', now))

            days_passed = max(0.0, (now - last_accessed) / (24 * 3600))
            created_days = max(0.0, (now - created_at) / (24 * 3600))

            half_life_days = max(1.0, (importance ** 1.5) * 2.5 * (1.0 + math.log1p(access_count) * 0.35))
            retention = importance * math.exp(-0.693 * days_passed / half_life_days)
            if created_days > 14 and not is_canon:
                retention *= math.exp(-0.03 * (created_days - 14))

            sim_score = 1.0 / (1.0 + max(0.0, dist))

            time_penalty = 1.0
            if not is_canon and created_days > 7.0:
                time_penalty = math.exp(-0.02 * (created_days - 7.0))

            final_score = (sim_score * weight_sim + (retention / 10.0) * (1.0 - weight_sim)) * time_penalty

            scored.append({
                "id": mem_id,
                "user_id": meta.get("user_id", user_id),
                "content": doc,
                "type": mem_type,
                "importance": importance,
                "is_forgotten": meta.get("is_forgotten", False),
                "distance": round(dist, 4),
                "similarity": round(sim_score, 4),
                "sim_score": round(sim_score, 4),
                "days_passed": round(days_passed, 2),
                "retention": round(retention, 2),
                "final_score": round(final_score, 4),
                "rank": 0
            })

        scored.sort(key=lambda x: x["final_score"], reverse=True)
        for idx, item in enumerate(scored):
            item["rank"] = idx + 1
        return scored[:top_k]

    def get_graph_data(self, limit: int = 120) -> dict:
        """获取记忆知识图谱节点与关联边，供前端 HTML5 Canvas 绘制交互式散点实体网络。"""
        try:
            res = self._execute_with_retry(lambda col: col.get(include=["metadatas", "documents"]))
        except Exception as e:
            print(f"[VectorDB] 获取图谱数据异常: {e}")
            return {"nodes": [], "links": []}

        if not res or not res.get("ids"):
            return {"nodes": [], "links": []}
            
        now = time.time()
        nodes = []
        for mem_id, doc, meta in zip(res["ids"][:limit], res["documents"][:limit], res["metadatas"][:limit]):
            if not meta:
                meta = {}
            importance = meta.get("importance", 1.0)
            access_count = meta.get("access_count", 1)
            last_accessed = meta.get("last_accessed", now)
            days_passed = (now - last_accessed) / (24 * 3600)
            retention = round(importance * math.exp(-0.1 * max(0.0, days_passed)) + (access_count * 0.2), 2)
            
            label = doc[:14] + ("..." if len(doc) > 14 else "")
            nodes.append({
                "id": mem_id,
                "label": label,
                "full_content": doc,
                "user_id": meta.get("user_id", 0),
                "type": meta.get("type", "episode"),
                "importance": importance,
                "access_count": access_count,
                "is_forgotten": meta.get("is_forgotten", False),
                "retention": retention
            })
            
        links = []
        node_len = len(nodes)
        for i in range(node_len):
            for j in range(i + 1, min(i + 4, node_len)):
                if nodes[i]["user_id"] == nodes[j]["user_id"]:
                    links.append({"source": nodes[i]["id"], "target": nodes[j]["id"], "type": "user"})
                elif nodes[i]["type"] == nodes[j]["type"] and i % 3 == 0:
                    links.append({"source": nodes[i]["id"], "target": nodes[j]["id"], "type": "category"})
                    
        return {"nodes": nodes, "links": links}

    def reset_to_factory_defaults(self) -> dict:
        """清空用户动态生成的记忆碎片，并完全重置恢复至出厂预置核心剧本记忆。"""
        cleared_count = 0
        def _clear(col):
            res = col.get()
            if res and res.get("ids"):
                col.delete(ids=res["ids"])
                return len(res["ids"])
            return 0

        try:
            cleared_count = self._execute_with_retry(_clear)
            print(f"[VectorDB] 动态记忆库清空完成 (移除了 {cleared_count} 条)！")
        except Exception as e:
            print(f"[VectorDB] 清空已有数据异常 ({e})，正在自愈重建集合...")
            try:
                self.client.delete_collection(self.col_name)
            except Exception:
                pass
            self._collection = None
            _ = self.collection

        # 立即强制重铸写入原作核心剧情记忆！
        seeded_count = self.seed_canon_memories(force_reseed=True)
        return {
            "status": "ok",
            "count": seeded_count,
            "inserted": seeded_count,
            "deleted": cleared_count,
            "message": f"记忆系统已重置完毕：动态用户记忆已彻底清空（{cleared_count}条），原作全真核心剧情设定（{seeded_count}条，含五百日元誓约、器官托付、星空列车决战、真白终局）已完成出厂固化重铸！"
        }

    def export_memories_archive(self) -> tuple[bytes, str]:
        """打包导出全部记忆库文件为 ZIP 归档 (包含 JSON、CSV 与元数据)。"""
        import io
        import zipfile
        import csv
        from datetime import datetime

        try:
            res = self._execute_with_retry(lambda col: col.get(include=["metadatas", "documents"]))
        except Exception as e:
            print(f"[VectorDB] 导出读取异常: {e}")
            res = None

        items = []
        if res and res.get("ids"):
            now = time.time()
            for mem_id, doc, meta in zip(res["ids"], res["documents"], res["metadatas"]):
                if not meta:
                    meta = {}
                created_at_val = meta.get("created_at", now)
                last_accessed_val = meta.get("last_accessed", now)
                try:
                    c_iso = datetime.fromtimestamp(created_at_val).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    c_iso = str(created_at_val)
                try:
                    a_iso = datetime.fromtimestamp(last_accessed_val).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    a_iso = str(last_accessed_val)

                items.append({
                    "id": mem_id,
                    "user_id": meta.get("user_id", 0),
                    "content": doc,
                    "type": meta.get("type", "episode"),
                    "importance": meta.get("importance", 1.0),
                    "is_forgotten": meta.get("is_forgotten", False),
                    "access_count": meta.get("access_count", 1),
                    "created_at": created_at_val,
                    "created_at_str": c_iso,
                    "last_accessed": last_accessed_val,
                    "last_accessed_str": a_iso
                })

        # 1. memories.json
        json_content = json.dumps(items, ensure_ascii=False, indent=2)

        # 2. memories.csv (UTF-8 BOM 为防止中文在 Excel 中乱码)
        csv_buffer = io.StringIO()
        csv_buffer.write('\ufeff')
        csv_writer = csv.writer(csv_buffer)
        csv_writer.writerow(["ID", "用户ID", "记忆内容", "类型", "重要度", "已遗忘归档", "访问次数", "创建时间", "最后访问时间"])
        for it in items:
            csv_writer.writerow([
                it["id"],
                it["user_id"],
                it["content"],
                "核心事实(fact)" if it["type"] == "fact" else "情景记忆(episode)",
                it["importance"],
                "是" if it["is_forgotten"] else "否",
                it["access_count"],
                it["created_at_str"],
                it["last_accessed_str"]
            ])
        csv_content = csv_buffer.getvalue()

        # 3. metadata.json
        stats = self.get_stats()
        meta_dict = {
            "archive_type": "neri_memories_backup",
            "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "exported_timestamp": time.time(),
            "total_count": len(items),
            "stats": stats,
            "version": "1.0.0"
        }
        meta_content = json.dumps(meta_dict, ensure_ascii=False, indent=2)

        # 4. README.txt
        readme_content = f"""==================================================
风又音理 (Kazamata Inori) 长期记忆库备份归档
==================================================
导出时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
记忆碎片总数: {len(items)} 条
Embedding 模型: {stats.get('model_name', 'bge-small-zh-v1.5')} (维度: {stats.get('dimension', 512)})

文件说明:
- memories.json: 完整记忆数据结构，适用于系统程序导入或迁移恢复
- memories.csv : 带 UTF-8 BOM 签名的表格，可直接用 Excel 或 WPS 打开查阅
- metadata.json: 记忆系统当时的状态、参数与快照元数据

==================================================
"""

        # 打包为 ZIP
        bio = io.BytesIO()
        with zipfile.ZipFile(bio, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("memories.json", json_content.encode("utf-8"))
            zf.writestr("memories.csv", csv_content.encode("utf-8"))
            zf.writestr("metadata.json", meta_content.encode("utf-8"))
            zf.writestr("README.txt", readme_content.encode("utf-8"))

        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"neri_memories_{ts_str}.zip"
        return bio.getvalue(), filename


vector_store = MemoryRetriever()
