# 安全策略

## 支持的版本

只维护 `main` 分支。接入方通过 `uses: luckliu2007/content-radar/.github/workflows/radar.yml@main` 调用，修复合并后即对所有接入仓库生效。

## 报告漏洞

请不要在公开 Issue 里披露漏洞细节。

1. 优先使用本仓库 **Security** 标签页的 “Report a vulnerability” 私密报告（[GitHub 说明](https://docs.github.com/zh/code-security/how-tos/report-and-fix-vulnerabilities/report-privately)）。
2. 如果这个入口不可用，开一个不含任何细节的 Issue，请维护者 [@luckliu2007](https://github.com/luckliu2007/luckliu2007) 与你私下联系。

我们会尽快确认收到，并在修复后说明影响范围。

## 范围

特别关心以下问题：

- 工作流获得了超出 `contents: write`、`issues: write` 的权限，或 Token 可能出现在日志、报告中；
- 第三方仓库的名称、简介或 README 内容能让雷达执行命令、修改文件，或者把不该引入的链接写进接入仓库；
- 跨 owner 转移的仓库被当作同一 owner 改名自动修复。
