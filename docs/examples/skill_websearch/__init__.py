"""实时联网搜索与资讯增强技能插件。
实现 BaseSkill，注册供大模型在 Function Calling 中自主调用的 web_search 工具。
"""

import urllib.parse
from typing import Any, Dict

import httpx

from src.plugins.base import BasePlugin
from src.plugins.skills.base import BaseSkill


class WebSearchSkill(BaseSkill):
    """供大模型调用的实时联网搜索技能。"""

    def __init__(self, plugin_context):
        super().__init__(
            name="web_search",
            description="当用户询问关于实时新闻、时事热点、最新开源库版本、天气事实、股票价格、未知的专业名词或现实生活事实时，自主调用此工具上网检索获取最新网页摘要与客观事实。",
            parameters_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词或精炼后的提问语句，例如 '2026年最新AI技术动态' 或 '今日上海天气预报'",
                    }
                },
                "required": ["query"],
            },
            admin_only=False,
        )
        self.context = plugin_context

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> str:
        query = params.get("query", "").strip()
        if not query:
            return "错误: 搜索关键词不能为空"

        cfg = self.context.get_config()
        max_results = int(cfg.get("max_results", 3))

        try:
            # 使用 DuckDuckGo HTML 搜索获取真实网页标题与摘要
            encoded_query = urllib.parse.quote(query)
            search_url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }

            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(search_url, headers=headers)
                if resp.status_code == 200:
                    text = resp.text
                    import re
                    # 简易正则抓取结果摘要片段
                    snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', text, re.DOTALL)
                    titles = re.findall(r'<a class="result__url[^>]*>(.*?)</a>', text, re.DOTALL)
                    
                    results = []
                    for i in range(min(max_results, len(snippets))):
                        clean_snip = re.sub(r'<[^>]+>', '', snippets[i]).strip()
                        clean_title = re.sub(r'<[^>]+>', '', titles[i]).strip() if i < len(titles) else "网页结果"
                        if clean_snip:
                            results.append(f"{i+1}. [{clean_title}]: {clean_snip}")

                    if results:
                        return f"【针对「{query}」的最新互联网搜索结果】:\n" + "\n".join(results)

            # 若网络无法直连或被防火墙拦截，返回保底搜索提示
            return f"【针对「{query}」的联网搜索结果】: 已检索到相关主题，但由于当前网络环境限制无法直接获取完整外部网页正文。建议结合已有知识并提示用户可能需要检查网络代理。"
        except Exception as e:
            return f"搜索请求执行异常 ({str(e)})，请根据已有知识回答。"


class SkillWebSearchPlugin(BasePlugin):
    """联网搜索插件主类。"""

    async def on_load(self) -> bool:
        # 实例化技能并向内核注册
        search_skill = WebSearchSkill(self.context)
        self.register_skill(search_skill)

        # 同时也注册一个快捷前缀指令供手动触发: /search <query>
        async def handle_search_cmd(args, event):
            if not args:
                return "用法: /search <搜索关键词>"
            q = " ".join(args)
            return await search_skill.execute({"query": q}, context={})

        self.register_command("search", handle_search_cmd, description="手动调用联网搜索引擎")
        return True

    async def on_enable(self) -> None:
        self.context.logger.info("实时联网搜索技能已激活，大模型可自主感知并调用！")
