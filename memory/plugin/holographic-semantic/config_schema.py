"""Desktop settings and the connection fields used by the embedding setup.

Hermes reads this file from disk and never imports it as a package: it may import only the pure-data module below.
"""

from dataclasses import replace

from plugins.memory.config_schema import (
    KIND_BOOL,
    KIND_NUMBER,
    KIND_SECRET,
    KIND_TEXT,
    STORAGE_PROVIDER,
    ProviderConfigSchema,
    ProviderField,
)


_ZH = {
    "semantic_tau": {
        "label": "相似度阈值",
        "description": "本地向量生效：事实需要达到的余弦相似度，范围为 0 到 1。更换本地模型后请重新初始化。",
    },
    "embedding_min_score": {
        "label": "云端最低相似度",
        "description": "云端向量生效：仅凭语义召回时的余弦相似度下限，范围为 -1 到 1。留空表示不设下限。",
    },
    "semantic_enabled": {
        "label": "语义召回",
        "description": "每轮开始前，本地向量侧车最多补充一条事实。数据留在本机。侧车不可用时使用关键词检索，从新会话起生效。",
    },
    "semantic_url": {
        "label": "本地侧车地址",
        "description": "本地向量服务的地址，一键部署后自动填写。上面的任务可为已有事实补建索引。",
    },
    "catalog_enabled": {
        "label": "事实目录",
        "description": "在系统提示词中用 #ID=标签列出可召回事实，智能体可用 fact_store get 查看全文。可与 MEMORY.md 同时开启，从新会话起生效。",
    },
    "catalog_max_tokens": {
        "label": "目录预算",
        "description": "事实目录的估算 token 上限。达到上限时优先保留可信度高的事实。下方是当前用量。",
    },
    "embedding_url": {"label": "向量 API 地址"},
    "embedding_model": {"label": "向量模型 ID"},
    "embedding_api_key": {
        "label": "API 密钥",
        "description": "留空时复用为该地址保存的密钥。官方 OpenAI 地址可复用当前档案已有的 OPENAI_API_KEY。",
    },
}

CONFIG_SCHEMA = ProviderConfigSchema(
    name="holographic-semantic",
    label="Holographic + semantic recall",
    storage=STORAGE_PROVIDER,  # the same config.yaml section the base provider reads (read/write_config_fields)
    connection_fields=("embedding_url", "embedding_model", "embedding_api_key"),
    connection_job="semantic-setup-local",
    # Every setting is inline, in the order a first setup goes: the Desktop shows the connection (the model) and
    # the jobs first, then these. So the threshold and its "Initialize threshold" job come right after the model,
    # the switch and the address a deployment already filled in follow, and the catalog's budget sits under its
    # switch with its use (usage_report binds that budget to catalog_max_tokens). Nothing is behind "Full config".
    fields=(
        ProviderField(
            "semantic_tau", "Similarity threshold", KIND_NUMBER, default="0.55", inline=True,
            description="Local embeddings: cosine similarity (0-1) a fact needs to be added by meaning. Initialize "
                        "it again after changing the local model."),
        ProviderField(
            "embedding_min_score", "Cloud minimum similarity", KIND_NUMBER, inline=True,
            description="Cloud embeddings: optional cosine floor (-1 to 1) for a fact recalled on meaning alone; "
                        "blank = none."),
        ProviderField(
            "semantic_enabled", "Semantic recall", KIND_BOOL, default="false", inline=True,
            description="Before a turn, add at most one fact from the local embedding sidecar. "
                        "Nothing leaves this machine; while the sidecar is down, recall stays by words. "
                        "Applies from the next session."),
        ProviderField(
            "semantic_url", "Sidecar address", KIND_TEXT, default="http://127.0.0.1:8791", inline=True,
            description="The local embedding service; one-click deployment fills it in. Index the facts already "
                        "stored with the job above."),
        ProviderField(
            "catalog_enabled", "Fact catalog", KIND_BOOL, default="false", inline=True,
            description="List every recallable fact as #id=label in the system prompt; the agent reads one in full "
                        "with fact_store get. MEMORY.md can stay on beside it. Applies from the next session."),
        ProviderField(
            "catalog_max_tokens", "Catalog budget", KIND_NUMBER, default="3000", inline=True,
            description="Estimated tokens the catalog may take; past it the lowest-trust facts are left out. Its "
                        "current use is shown below."),
        ProviderField("embedding_url", "Embedding API URL", default="https://api.openai.com/v1"),
        ProviderField("embedding_model", "Embedding model ID", default="text-embedding-3-small"),
        # No env_key: the setup itself stores the key, and settings.read() marks the field set per endpoint.
        ProviderField("embedding_api_key", "API key", KIND_SECRET,
                      description="Leave blank to reuse the key saved for this address. The official OpenAI address "
                                  "can reuse this profile's OPENAI_API_KEY."),
    ),
)

CONFIG_SCHEMA = replace(
    CONFIG_SCHEMA,
    translations={"zh": {"label": "Holographic 语义召回"}},
    fields=tuple(replace(field, translations={"zh": _ZH[field.key]}) for field in CONFIG_SCHEMA.fields),
)
