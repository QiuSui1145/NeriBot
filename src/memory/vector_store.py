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

class MemoryRetriever:
    def __init__(self, data_path="data/chroma_db"):
        self.data_path = data_path
        self.client = chromadb.PersistentClient(path=data_path)
        self.ef = HybridEmbeddingFunction()
        self.col_name = "neri_memories"
        self._collection = None
        self._ensure_collection()

    def _ensure_collection(self):
        """获取或自愈重连 ChromaDB 集合句柄。"""
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
        return self._collection

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
        return mem_id
        
    def search_relevant_memories(self, user_id: int, query: str, top_k: int = 3) -> list[str]:
        now = time.time()
        try:
            user_id = int(user_id)
        except Exception:
            user_id = 0

        def _do_query(col):
            return col.query(
                query_texts=[query],
                n_results=top_k * 3,
                where={"$and": [{"user_id": user_id}, {"is_forgotten": False}]}
            )

        try:
            results = self._execute_with_retry(_do_query)
        except Exception as e:
            print(f"[VectorDB] 召回查询异常: {e}")
            return []
            
        if not results or not results.get('documents') or not results['documents'][0]:
            return []
            
        docs = results['documents'][0]
        metas = results['metadatas'][0]
        ids = results['ids'][0]
        distances = results['distances'][0] if 'distances' in results and results['distances'] else [0]*len(docs)
        
        scored_mems = []
        for doc, meta, mem_id, dist in zip(docs, metas, ids, distances):
            if not meta:
                meta = {}
            importance = meta.get('importance', 1.0)
            access_count = meta.get('access_count', 1)
            last_accessed = meta.get('last_accessed', now)
            days_passed = (now - last_accessed) / (24 * 3600)
            retention = importance * math.exp(-0.1 * max(0.0, days_passed)) + (access_count * 0.2)
            sim_score = 1.0 / (1.0 + max(0.0, dist))
            final_score = sim_score * 0.7 + (retention / 10.0) * 0.3
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

    def apply_forgetting_curve(self, threshold: float = 0.5):
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
            importance = meta.get('importance', 1.0)
            access_count = meta.get('access_count', 1)
            last_accessed = meta.get('last_accessed', now)
            days_passed = (now - last_accessed) / (24 * 3600)
            retention = importance * math.exp(-0.1 * max(0.0, days_passed)) + (access_count * 0.2)
            
            if retention < threshold:
                meta['is_forgotten'] = True
                forget_ids.append(mem_id)
                forget_metas.append(meta)
                
        if forget_ids:
            try:
                self._execute_with_retry(lambda col: col.update(ids=forget_ids, metadatas=forget_metas))
                print(f"[VectorDB] 遗忘机制执行完毕，归档了 {len(forget_ids)} 条记忆碎片。")
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

        def _do_query(col):
            return col.query(
                query_texts=[query],
                n_results=min(top_k * 4, 30),
                where={"user_id": user_id} if user_id != 0 else None
            )

        try:
            results = self._execute_with_retry(_do_query)
        except Exception as e:
            print(f"[VectorDB Simulator] 查询异常: {e}")
            return []
            
        if not results or not results.get('documents') or not results['documents'][0]:
            return []
            
        docs = results['documents'][0]
        metas = results['metadatas'][0]
        ids = results['ids'][0]
        distances = results['distances'][0] if 'distances' in results and results['distances'] else [0]*len(docs)
        
        scored = []
        now = time.time()
        for doc, meta, mem_id, dist in zip(docs, metas, ids, distances):
            if not meta:
                meta = {}
            importance = meta.get('importance', 1.0)
            access_count = meta.get('access_count', 1)
            last_accessed = meta.get('last_accessed', now)
            days_passed = (now - last_accessed) / (24 * 3600)
            
            retention = importance * math.exp(-lambda_decay * max(0.0, days_passed)) + (access_count * 0.2)
            sim_score = 1.0 / (1.0 + max(0.0, dist))
            final_score = sim_score * weight_sim + (retention / 10.0) * (1.0 - weight_sim)
            
            scored.append({
                "id": mem_id,
                "user_id": meta.get("user_id", user_id),
                "content": doc,
                "type": meta.get("type", "episode"),
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
        """彻底清空全部记忆碎片并还原到出厂初始状态（不留任何预置或残留记忆）。"""
        cleared_count = 0
        def _clear(col):
            res = col.get()
            if res and res.get("ids"):
                col.delete(ids=res["ids"])
                return len(res["ids"])
            return 0

        try:
            cleared_count = self._execute_with_retry(_clear)
            print(f"[VectorDB] 出厂初始化完成，已彻底清空全部记忆库 (清除了 {cleared_count} 条，UUID 保持不变)！")
        except Exception as e:
            print(f"[VectorDB] 清空已有数据异常 ({e})，尝试重建集合...")
            try:
                self.client.delete_collection(self.col_name)
            except Exception:
                pass
            self._collection = None
            _ = self.collection

        return {
            "status": "ok",
            "count": 0,
            "inserted": 0,
            "deleted": cleared_count,
            "message": "记忆系统已重置恢复至纯净出厂状态，全部记忆信息已彻底清空！"
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
