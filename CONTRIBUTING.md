# 贡献指南

欢迎报告误报、漏报，或改进健康检查和候选筛选规则。参与前请先读 [行为准则](CODE_OF_CONDUCT.md)。

## 设计原则

- **只依赖 Python 标准库**，接入方不需要安装任何依赖。
- **只报告，不替人决定**：雷达只标记问题、列出候选，收录与否由人工审核决定。
- **宁可漏报，不可误改**：只有同一 owner 下的改名才自动修复链接；跨 owner 转移一律只报警。
- **调用方权限最小**：只用 `github.token`，只需要 `contents: write` 和 `issues: write`。

## 本地开发

```bash
# 对任意一个接入仓库跑一次（不加 --apply-renames 就不会改文件）
cd ../English-study
GITHUB_TOKEN=$(gh auth token) python ../content-radar/radar.py --config .github/radar.json --out radar-report
```

报告写在 `radar-report/` 下。改动检测逻辑时，用两三个接入仓库各跑一次，对比改动前后的报告。

## 提交前检查

- `python -m py_compile radar.py` 通过。
- 新增配置项时，同步更新 README 的“配置示例”，并给出默认值（老的 `radar.json` 不改也要能跑）。
- 不在日志或报告里输出 Token。

## 报告问题

用 [问题报告](https://github.com/luckliu2007/content-radar/issues/new?template=bug-report.yml) 或 [功能建议](https://github.com/luckliu2007/content-radar/issues/new?template=feature-request.yml) 表单。安全问题请按 [SECURITY.md](SECURITY.md) 私下报告，不要开公开 Issue。
