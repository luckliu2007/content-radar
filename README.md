# content-radar

每日内容雷达：为 luckliu2007 的学习资源仓库自动做两件事。

1. **健康检查**：扫描仓库里引用的所有 GitHub 项目，标记已归档、已删除、长期未更新、改名或转移的项目。**同一 owner 下的改名自动修复链接**；转移到其他 owner 的只标记不跟随（防止仿冒或被接管的仓库被自动引入）。
2. **发现候选**：按各仓库 `.github/radar.json` 里配置的主题搜索 GitHub，筛选近期活跃、达到星标门槛、非 fork 非归档的新项目，按每日星标增速排序。增速异常的项目会标记“⚠️ 增长异常”，提示可能刷星或炒作。

结果以 Issue（标签 `content-radar`）发布在各仓库，供后续审核与收录流程处理。

## 接入一个仓库

1. 添加 `.github/radar.json`（主题、搜索词、门槛，见下例）；
2. 添加 `.github/workflows/content-radar.yml`：

```yaml
name: Content Radar
on:
  schedule:
    - cron: '0 1 * * *'
  workflow_dispatch:
permissions:
  contents: write
  issues: write
jobs:
  radar:
    uses: luckliu2007/content-radar/.github/workflows/radar.yml@main
```

3. 不想再看到的候选，逐行写进 `.github/radar-ignore.txt`（`owner/repo`）。

## 配置示例

```json
{
  "theme": "主题说明，写进报告",
  "self_owner": "luckliu2007",
  "queries": ["topic:ai-agents", "topic:mcp"],
  "min_stars": 3000,
  "pushed_within_days": 30,
  "max_age_days": 730,
  "stale_days": 540,
  "suspicious_stars_per_day": 500,
  "top_n": 8,
  "verified_transfers": {"OldOwner/repo": "NewOwner/repo"}
}
```

`verified_transfers`：人工核实过的跨 owner 转移（例如官方迁移），目标一致时不再报警；若仓库再次转移到其他地方，会重新报警。

## 本地运行

```bash
GITHUB_TOKEN=$(gh auth token) python radar.py --config .github/radar.json --out radar-report
```

只依赖 Python 标准库。
