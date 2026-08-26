# docs/visions · 版本与当前状态

最后核对：2026-08-26（main @ `fef4e12`，CI 绿，`./scripts/check.sh` 本地全绿）。

## 里程碑状态

M1（抽取）/ M2（报告）/ M3（候选筛选）/ M5（可视化）**全部完成且实测过**。
M4 是可选项，默认不启动（plan.md §7）。

2026-08-26 本机快照全量复跑（extract 222.7s）：

| 项 | 值 |
| --- | --- |
| 落库命令 | 61,772（解析降级 269，脱敏 1,855） |
| 可用于耗时统计 | 50,330 |
| 判定为失败 | 2,309 |
| 候选 | 86（preventable 42 / wait_polling 15 / hotspots 12 / repeated 10 / timeout 7） |
| report.html | 1,939 KB，离线单文件 |

## 当前阶段：修复整合期（v0.6-fix-consolidation）

不是写新功能，是把已完成的修复交付到远端。详见
[v0.6-fix-consolidation/README.md](v0.6-fix-consolidation/README.md)。

要点：

1. **PR #48 已合并**（remedy digest，2026-08-25/26），#46 可关。
2. **12 条 issue 修复分支仍压在 `~/Documents/ChatGPT/cmdaudit` 本地未推送**——
   合并入口顺序与冲突面清单见该目录 `HANDOFF.md` / `~/Documents/handoff-cmdaudit-2026-08-25.md`。
   合并后旧口径数字全部作废，需同一快照重跑再统一重写 README。
3. open issue 18 个；合并完 12 条分支后可关一批（#6/#7/#11–#13/#17/#21–#24/#29/#30）。
4. 剩余新账：#44（finding 快照序）、#45（耗时线按需加载）、#47（M6–M8 路线）、
   #49（看板 remedy 呈现）、#50（数字边界归一化）。
5. 2026-08-26 前端审查：[`docs/reviews/2026-08-26-frontend-audit.md`](../reviews/2026-08-26-frontend-audit.md)，
   与 #21/#23/#44/#45/#49 互为代码佐证，另有新发现（payload 浅合并无校验、键盘作用域泄漏、
   窄视口看板横向溢出等）。
