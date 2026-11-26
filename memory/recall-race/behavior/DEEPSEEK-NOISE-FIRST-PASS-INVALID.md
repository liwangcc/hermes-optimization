# 噪声探针首轮：自动评分器缺陷与封存说明

首轮 9/16 逻辑会话后，N05 official_noisy 第二轮 `finish_reason=length`，1536 completion tokens 全为 reasoning、可见 content 为空。按预注册停止条件封存，未继续派发。

同时发现自动 forbidden 字符串判据有语义缺陷：模型写“旧笔记说统一返回 XML，但已过期、不采用”会被误判为采纳噪声；写“不要写 config.py”也会因出现 config.py 被误判。required 的长短语同义改写也被误判缺失（如“不重建生产表” vs “不直接重建生产表”）。

因此首轮的 task_pass/forbidden_hit 聚合**作废，不作为质量结论**。保留原始回执与答案供人工语义复核；客观 get/search 行为、usage、耗时仍可用。后续若重跑，须先冻结语义 rubric（区分采纳/拒绝提及、同义锚点），并提高输出预算或限制思考，另行授权，不自动重试本轮。
