# 单品自然周投产报告 Skill

将已填写的每日综合投产登记 `.xlsx` 汇总成周一至周日的单文件离线 HTML。默认保留单品选择、三张每日趋势图、前 10 单品热力表及展开的其余单品。周投产按销售总额除以费用总额计算。

## 安装和运行

跨设备下载入口：[v0.1.0 简易版安装包](https://github.com/Ninaix0217/weekly-product-roi-report-skill/releases/tag/v0.1.0)。从 Assets 下载 `weekly-product-roi-report-v0.1.0.zip`，不要使用聊天中的本机 `C:/...` 文件链接。

本仓库为私有仓库，目标设备浏览器须登录 `Ninaix0217` 或有该仓库访问权限的账号。未授权访问可能返回 404。若使用 skill-installer，指定 `--repo Ninaix0217/weekly-product-roi-report-skill --ref v0.1.0 --path weekly-product-roi-report`，并使用目标设备已有的 GitHub 凭据；本仓库没有 `main` 分支，当前默认分支是 `codex/initial-skill`。

复制本仓库的 `weekly-product-roi-report/` 到 Codex 的 skills 目录，重新加载技能列表。Python 3.10+；安装依赖仅需：

```text
python -m venv .venv
<venv-python> -m pip install -r weekly-product-roi-report/requirements.txt
<venv-python> weekly-product-roi-report/scripts/weekly_roi.py preflight
<venv-python> weekly-product-roi-report/scripts/weekly_roi.py run --input-dir <日报文件夹> --week-start <周一日期> --output-dir <新的运行目录>
```

Windows 的 venv-python 是 `.venv/Scripts/python.exe`，Linux/macOS 是 `.venv/bin/python`。在已有合适环境中无需建立 venv。输出目录不能已存在；原表和先前报告都保留。

输出 HTML 的数据、图表库和样式均内嵌，复制 HTML 到另一台设备即可打开。当前版本不实现周环比、经营状态或筛选，完整输入规则和验证范围见 [SKILL.md](weekly-product-roi-report/SKILL.md) 与 [schema.md](weekly-product-roi-report/references/schema.md)。

## 测试

```text
<venv-python> -I -m unittest discover -s tests -v
node weekly-product-roi-report/scripts/browser_smoke.cjs --html <生成的HTML> --analysis <analysis.json> --screenshots <截图目录> --playwright-module <Playwright模块路径> --browser-channel msedge
```

单元测试仅使用人工合成的 OOXML 工作簿，测试跨月自然周、金额/比值、缺失和重复输入、SKU 冲突、缓存漂移、无费用和转义边界。浏览器脚本需要现有 Playwright 与浏览器；不把机器专用运行时打包进技能。默认用 Playwright 配套 Chromium，也可显式选已安装的 Edge/Chrome。

仓库不含真实经营数据。私有真实数据的复现结果在 [VALIDATION.md](VALIDATION.md) 中记录验证层级；不应从合成测试或缓存校验推断上游流水真实性。

图表依赖 D3 7.9.0，许可证见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
