"""内容雷达：检查仓库已收录的 GitHub 项目健康度，并按主题发现新的优质项目。

用法：
    python radar.py --config .github/radar.json --out radar-report [--apply-renames]

只依赖标准库。需要环境变量 GITHUB_TOKEN（Actions 自带）以提高 API 限额。
输出：
    <out>.md    人类可读报告（用作 Issue 正文）
    <out>.json  结构化结果（供后续自动处理）
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.github.com"
LINK_RE = re.compile(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)")
# 链接里出现这些 owner 视为占位符或本人仓库，不做检查
SKIP_OWNERS = {"owner", "your_name", "your-name", "user", "username"}
SCAN_GLOBS = ("**/*.md", "content/*.json")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def api_get(path, params=None):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "content-radar"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in (403, 429) and attempt < 2:  # 限流：等一会儿重试
                time.sleep(20 * (attempt + 1))
                continue
            raise
        except urllib.error.URLError:
            if attempt < 2:
                time.sleep(5)
                continue
            raise


def listed_repos(root, self_owner):
    """返回 {owner/repo 小写: (原始写法, {出现的文件})}。"""
    found = {}
    for pattern in SCAN_GLOBS:
        for f in root.glob(pattern):
            if any(part.startswith(".") for part in f.relative_to(root).parts[:-1]):
                continue
            text = f.read_text(encoding="utf-8", errors="ignore")
            for owner, repo in LINK_RE.findall(text):
                repo = repo.removesuffix(".git")
                if owner.lower() in SKIP_OWNERS or owner.lower() == self_owner.lower():
                    continue
                key = f"{owner}/{repo}".lower()
                found.setdefault(key, (f"{owner}/{repo}", set()))[1].add(str(f.relative_to(root)))
    return found


def days_since(iso):
    return (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))).days


def health_check(listed, stale_days, verified_transfers=None):
    verified = {k.lower(): v.lower() for k, v in (verified_transfers or {}).items()}
    issues = []
    for key, (orig, files) in sorted(listed.items()):
        info = api_get(f"/repos/{orig}")
        base = {"repo": orig, "files": sorted(files)}
        if info is None:
            issues.append({**base, "kind": "missing"})
            continue
        new_name = info["full_name"]
        # 人工核实过的跨 owner 转移：目标一致就不再报警；目标再变则重新报警
        if new_name.lower() != key and verified.get(key) != new_name.lower():
            same_owner = new_name.split("/")[0].lower() == orig.split("/")[0].lower()
            issues.append({**base, "kind": "renamed" if same_owner else "transferred", "new": new_name})
        if info.get("archived"):
            issues.append({**base, "kind": "archived"})
        elif days_since(info["pushed_at"]) > stale_days:
            issues.append({**base, "kind": "stale", "pushed_at": info["pushed_at"][:10]})
    return issues


def relevant(text, cfg):
    """按主题关键词判断候选是否相关：require_keywords 至少命中一个，exclude_keywords 一个都不能命中。"""
    text = text.lower()
    req = [k.lower() for k in cfg.get("require_keywords", [])]
    exc = [k.lower() for k in cfg.get("exclude_keywords", [])]
    if req and not any(k in text for k in req):
        return False
    return not any(k in text for k in exc)


def discover(cfg, listed, ignore):
    """返回 (候选列表, 因主题不相关被过滤的数量)。"""
    since = (dt.date.today() - dt.timedelta(days=cfg.get("pushed_within_days", 30))).isoformat()
    seen, cands, filtered = set(), [], 0
    for q in cfg["queries"]:
        query = f"{q} stars:>={cfg.get('min_stars', 500)} pushed:>={since} archived:false fork:false"
        res = api_get("/search/repositories", {"q": query, "sort": "stars", "order": "desc", "per_page": 30}) or {}
        for it in res.get("items", []):
            key = it["full_name"].lower()
            if key in seen or key in listed or key in ignore or not it.get("description"):
                continue
            seen.add(key)
            age = max(days_since(it["created_at"]), 30)
            if age > cfg.get("max_age_days", 730):
                continue
            if not relevant(it["description"] + " " + " ".join(it.get("topics") or []), cfg):
                filtered += 1
                continue
            lic = (it.get("license") or {}).get("spdx_id")
            cands.append({
                "repo": it["full_name"],
                "url": it["html_url"],
                "stars": it["stargazers_count"],
                "created": it["created_at"][:10],
                "pushed": it["pushed_at"][:10],
                "license": lic or "-",
                "stars_per_day": round(it["stargazers_count"] / age, 1),
                # 增速远超正常水平的项目常见于刷星或短期炒作，标记出来供审核时重点核实
                "suspicious_growth": it["stargazers_count"] / age > cfg.get("suspicious_stars_per_day", 500),
                "description": it["description"].strip()[:200],
                "query": q,
            })
        time.sleep(2)  # 搜索 API 限额 30 次/分钟
    cands.sort(key=lambda c: c["stars_per_day"], reverse=True)
    return cands[: cfg.get("top_n", 8)], filtered


def apply_renames(root, issues):
    """只自动修复同一 owner 下的改名；跨 owner 转移需人工判断，不自动跟随。"""
    changed = set()
    for i in issues:
        if i["kind"] != "renamed":
            continue
        old_url, new_url = f"https://github.com/{i['repo']}", f"https://github.com/{i['new']}"
        pat = re.compile(re.escape(old_url) + r"(?=[/)\s>\]\"'#?]|$)", re.IGNORECASE)
        for rel in i["files"]:
            if not rel.endswith(".md"):  # 结构化数据（如带哈希清单的 JSON）留给人工/审核流程处理
                continue
            p = root / rel
            text = p.read_text(encoding="utf-8")
            new_text = pat.sub(new_url, text)
            if new_text != text:
                p.write_text(new_text, encoding="utf-8", newline="")
                changed.add(rel)
    return sorted(changed)


KIND_LABEL = {
    "renamed": "🔁 改名（同一 owner，可自动修复）",
    "transferred": "⚠️ 转移到其他 owner（需人工核实，可能是仿冒或被接管）",
    "archived": "🗄️ 已归档",
    "stale": "💤 长期未更新",
    "missing": "❌ 已删除或私有",
}


def render(cfg, issues, cands, applied, filtered=0):
    today = dt.date.today().isoformat()
    lines = [f"# 内容雷达 {today}", "", f"主题：{cfg.get('theme', '')}", ""]
    lines += ["## 一、已收录项目健康检查", ""]
    if not issues:
        lines.append("全部正常。")
    else:
        lines += ["| 项目 | 问题 | 详情 | 出现位置 |", "| --- | --- | --- | --- |"]
        for i in issues:
            detail = i.get("new") or i.get("pushed_at", "")
            lines.append(f"| `{i['repo']}` | {KIND_LABEL[i['kind']]} | {detail} | {', '.join(i['files'])} |")
    if applied:
        lines += ["", f"已自动修复改名链接：{', '.join(applied)}"]
    lines += ["", "## 二、新发现候选（按每日星标增速排序）", ""]
    if filtered:
        lines += [f"已按主题关键词过滤掉 {filtered} 个不相关项目。", ""]
    if not cands:
        lines.append("今日无新候选。")
    else:
        lines += ["| 项目 | 星标 | 星/天 | 创建 | 最近提交 | 许可证 | 简介 |", "| --- | --- | --- | --- | --- | --- | --- |"]
        for c in cands:
            desc = c["description"].replace("|", "/")
            flag = " ⚠️ 增长异常" if c.get("suspicious_growth") else ""
            lines.append(f"| [{c['repo']}]({c['url']}) | {c['stars']} | {c['stars_per_day']}{flag} | {c['created']} | {c['pushed']} | {c['license']} | {desc} |")
    lines += ["", "---", "候选仅表示数据层面值得关注，是否收录由后续审核流程决定。不想再看到的项目，加到 `.github/radar-ignore.txt`。"]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=".github/radar.json")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="radar-report")
    ap.add_argument("--apply-renames", action="store_true")
    args = ap.parse_args()

    root = Path(args.root)
    cfg = json.loads((root / args.config).read_text(encoding="utf-8"))
    ignore_file = root / ".github/radar-ignore.txt"
    ignore = set()
    if ignore_file.exists():
        ignore = {l.strip().lower() for l in ignore_file.read_text(encoding="utf-8").splitlines()
                  if l.strip() and not l.startswith("#")}

    listed = listed_repos(root, cfg.get("self_owner", ""))
    issues = health_check(listed, cfg.get("stale_days", 540), cfg.get("verified_transfers"))
    cands, filtered = discover(cfg, listed, ignore)
    applied = apply_renames(root, issues) if args.apply_renames else []

    Path(args.out + ".md").write_text(render(cfg, issues, cands, applied, filtered), encoding="utf-8")
    Path(args.out + ".json").write_text(json.dumps(
        {"date": dt.date.today().isoformat(), "listed": len(listed), "issues": issues,
         "candidates": cands, "filtered_irrelevant": filtered, "applied_renames": applied}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"listed={len(listed)} issues={len(issues)} candidates={len(cands)} filtered={filtered} renamed_fixed={len(applied)}")


if __name__ == "__main__":
    main()
