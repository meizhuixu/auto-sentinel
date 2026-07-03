# Auto Sentinel — Project Context & Status

> 项目上下文 + 进度快照。**维护规则：每次代码 PR 落地，顺手更新「当前状态」段和涉及的决策段。**
> 权威进度以 `git log` / `specs/<sprint>/tasks.md` 的 `[X]` / `DEBT.md` 为准，本文件是快照 + 上下文入口。
> 矩阵全局上下文见 `~/Repo/PORTFOLIO.md`（本地文件，不入库）。

---

## 当前状态（快照 2026-07-03，Sprint 6 完成）

- ✅ **Sprint 6（Fix Verification Integrity & Pipeline Consolidation）完成并合并**：
  **PR #19 已 merge，main 在 `481a08a`**，tasks.md 38/38 全部 `[X]`，feature 分支已删。
  SDD 全流程（`specs/006-fix-verification-integrity/`：spec/plan/tasks/contracts 齐全）。
  对应 `~/Repo/PORTFOLIO.md` M2 的完成标准均达成：CI 全绿 + re-baseline 诚实数字入 README。
- ✅ **fix-artifact ↔ Verifier 契约修复（US1，双保险）**：契约=完整可运行脚本
  （`contracts/fix-artifact.md`）。生产侧 prompt + compile() 校验 + 单次重试
  （`_producer_contract.py`）；Verifier 侧确定性规范化（`_artifact_normalizer.py`：
  verbatim/wrapped/rejected）+ 落盘挂载执行（替掉 `python -c`）。真实 008 验证：exit 0、
  outcome verbatim。
- ✅ **诚实 re-baseline 完成（run_id `20260703-193916-4a165e7`，¥1.84）**：
  `resolved` 收紧为要求沙盒 exit 0 → **resolution_rate 0.62**（CODE 12/12=1.00、INFRA 0.60、
  SECURITY 0.50、CONFIG 0.40），P50 49.4s / P95 89.8s，SC-013 漏报=0，
  **格式性 SyntaxError 失败=0（SC-001 达成）**。旧 0.98 是完成率口径，已降为 README 历史脚注。
  未解决的 19 个全是诚实的沙盒边界（目标系统配置/网络/第三方包在 alpine 沙盒不存在）+1 个 LLM 超时。
- ✅ **v1 单代理管线退役（US4）**：`graph.py`/`nodes/{analyze_error,execute_fix}.py`/
  `DiagnosticState`/`AUTOSENTINEL_MULTI_AGENT` 全删；`nodes/{parse_log,format_report}.py`
  保留（v2 共用）。**Constitution 2.2.0 → 2.3.0**（I 与 VII.1 的 grandfathering 条款移除）。
- ✅ **broad CI 落地（US3）**：`.github/workflows/ci.yml` = ruff + mypy + 全量 pytest
  （含两个 AST 边界 gate）+ :5434 Postgres service + `AUTOSENTINEL_REQUIRE_CHECKPOINTER=1`
  防静默 skip（要求时 DB 不可达 = 红，实测验证）。**已在 PR #19 上实测转绿**（首跑因
  `uv run` 隐式 re-sync 撞 CI 上不存在的 `../llmops-dashboard` 路径依赖而红，
  `uv sync --frozen` + `uv run --no-sync` 双闸修复；test job 日志确认 checkpointer
  跨进程测试真实执行、无静默 skip）。
- ✅ DX 小项（US5）：factory 配置路径锚定包内、CLAUDE.md Onboarding/Sprint Start 文档、
  `setup-plan.sh` 防覆盖闸（`--force` 才能覆写已填充 plan.md）。
- 🔑 `ARK_API_KEY` 已在本地 `.env` 配置（矩阵中唯一已配 key 的项目）。
- ⚠️ 新记 DEBT：`AgentState.fix_script` 残留字段、mypy 基线偏松（typeddict-item 豁免）、
  `cost_accumulated` 镜像在成功 run 里恒 0（CostGuard 本体正常，benchmark 计费不受影响）。
- 下一步：本项目暂告一段落（M2 完成，PORTFOLIO.md 的 M2 勾选由 owner 维护）；
  矩阵下一站按 `~/Repo/PORTFOLIO.md` 进 **M3（DevDocs RAG Phase 6）**——不同仓库，
  按红线「一个 chat 不同时推多个项目」应在该仓库新开会话。本仓库再动大概率是
  M4（DevContext MCP Phase 2 经 HTTP 调 `analyze_error_log` 等 3 个 tool）或
  M5 端到端 demo。

---

## 项目是什么

故障自动响应系统：输入报错日志 → 自动分析、写修复代码、安全审查、Docker 沙盒验证，全程无人介入。
6 个 agent 用 LangGraph 编排，agent 间只走 state channel（AST 静态分析在 CI 强制，非口头约定）。

| Agent | 职责 | 真实 LLM |
|-------|------|----------|
| Diagnosis | 解析 stack trace，分类错误 | ✅ |
| Supervisor | 路由到对应 specialist | ✅ |
| CodeFixer | CODE / SECURITY / UNKNOWN | ✅ |
| InfraSRE | INFRA / CONFIG | ✅ |
| SecurityReviewer | 所有 fix 必经 SAFE/HIGH_RISK 审查 | ✅（reasoning model） |
| **Verifier** | Docker 沙盒跑测试，唯一允许 import docker | ❌ 保持确定性（exit code 判定） |

HIGH_RISK 触发 LangGraph `interrupt()`，PostgresSaver 支持跨进程 `Command(resume=...)` 恢复。

## 方法论

**SDD (Spec Kit)**：Constitution 项目级一次立项（现为 v2.3.0——Sprint 6 移除了 I/VII.1
的 v1 grandfathering 条款），每个 Sprint 必走
/specify → /plan → /tasks → /implement，不可跳过。Constitution v2.2.0 起的 Principle VII
（LLM Provider Boundary & Cost Governance）：VII.1 Provider Isolation（AST 强制 SDK import
仅限 `src/auto_sentinel/llm/`）/ VII.2 Cost Guard 不可绕过 / VII.3 Trace Propagation 强制 /
VII.4 Model Routing 声明式。

## Sprint 5 关键决策（已落地）

- **模型路由（3 endpoint × 6 agent，单网关火山方舟）**：Supervisor/Verifier → Doubao-1.5-lite-32k；
  Diagnosis/CodeFixer/InfraSRE → Doubao-Seed-2.0-pro；SecurityReviewer → GLM-4.7（reasoning，
  经火山方舟代理，非智谱官方网关）。OpenAI SDK + base_url 指向 Ark，单一 `ARK_API_KEY`。
  路由配置在 `config/model_routing.yaml`（声明式，不在 agent 内硬编码）。
- **原生货币计量**：cost 按模型计费货币记账（Ark 系全 CNY），零汇率换算，数据结构带 currency 字段。
  Sprint 5 预算 ¥150，CostGuard 超阈值抛 `CostGuardError`，`cost_exhausted_node` + `_guarded`
  wrapper 经条件边确定性中止。GLM-4.7 单价按 ¥3/¥14 主档记（输出 >200，三档见 pricing 注释）。
- **trace_id 单一来源**：trace_id == job_id == `secrets.token_hex(16)`（32-hex，OTel 兼容），
  incident 入口一次生成，经 state channel 透传，LLMTracer 不自生成。
- **env-gated checkpointer**：`AUTOSENTINEL_CHECKPOINTER_DSN` 设了走 PostgresSaver（durable），
  没设走 MemorySaver（hermetic）。`build_multi_agent_graph(agents=)` 是测试注入缝（D2）。
- **SC-013 / SECURITY 子集（T066 真跑后修订）**：030/031/033 重标 SAFE（gate 判 fix artifact 而非
  incident）；032/034/035（涉密类）加确定性 secret/credential 关键词 override 强制 HIGH_RISK +
  GLM 调用失败时 fail-safe HIGH_RISK。HIGH_RISK 子集现为 032/034/035，SC-013=0 由确定性机制保证。
- **benchmark fixture**：`data/benchmark/*.json` 为显式 tracked authored data（`git add -f`），
  ground truth 人工标注，AI 不得自生成自验证。

## 技术栈

LangGraph / OpenAI SDK（base_url→火山方舟）/ Docker SDK / Pydantic v2 / PostgreSQL（checkpointer）/
Langfuse（自托管，项目 4）/ pytest 100% branch coverage / GitHub Actions（Sprint 6 起 broad CI：
ruff + mypy + 全量 pytest + AST 边界 gate + :5434 checkpointer service；另有 scenario-authorship
gate）/ uv

## 跨项目依赖

- **项目 4 LLMOps Dashboard**：`llmops_dashboard` 作为可选 tracing extra，`set_cost_breakdown`
  签名两仓已对齐（keyword-only，currency 默认 CNY）。T068 冒烟脚本验证真实 trace 进 Langfuse。
- **项目 3 DevContext MCP**：Phase 2 将通过 HTTP 调用本项目（`analyze_error_log` 等 3 个 tool）。
