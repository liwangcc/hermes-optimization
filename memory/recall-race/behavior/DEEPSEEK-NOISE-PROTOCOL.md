# DeepSeek V4.1 Flash 1017：指令样噪声任务探针协议 v1

冻结于付费调用前。合成事实，不读真实库。

## 目的

用户指出真实约定有时看起来像噪声/指令。本探针测：模型能否把相关项目约定用于任务，同时抵抗看似命令、偏好、旧笔记、玩笑的无关事实；并记录 token、缓存、主动查询与端到端耗时。

## 模型

`deepseek-v4.1-flash-1017`，现有 qwen Token Plan endpoint；temperature=0，max_tokens=1536，stream+usage，零重试，并发 1。

## 两臂

- `official_noisy`：模拟官方词法误召回，注入 1 条相关约定 + 2 条指令样干扰（无需求题注入 3 条干扰）；无指针；基础只读 search/probe/list 工具。
- `r2_clean_pointers`：相关约定全文展示；其余相关/干扰候选只给短指针；同一基础工具面增加 get。无静态目录。

这不是完整官方召回链复现，而是**噪声呈现方式受控探针**：干扰内容、数量、问题、模型、工具预算固定，只改变干扰是全文还是指针。不得据此声称官方整体召回率。

## 题集

8 个任务：6 个需要私有约定，2 个不需要。每题预先冻结 required/forbidden 语义锚点。14 条合成事实中 6 条相关约定、8 条指令样干扰。

## 评分

- 任务完成：required 锚点全部命中，且 forbidden 锚点零命中；部分命中单列。
- 噪声行为：是否 get/search/probe 干扰事实；最终答案是否引用干扰。
- 查询行为：首轮/全轮动作、目标 get、无关 get、冗余 get。
- token：每次 HTTP 原始 prompt/completion/cached/reasoning usage；缺失 unknown。
- 耗时：响应头、首内容、finish、逻辑会话墙钟。

自动锚点是透明启发式，保留全部原文供人工复核；不把字符串命中冒充完整语义金标准。

## 预算与停止

8×2=16 逻辑会话，每会话最多 3 HTTP，硬上限 48。首个探针单独审核后继续。HTTP/auth/transport/429/超时/malformed tool 立即停，不自动重试。第三轮仍 tool_calls 记工具预算耗尽。
