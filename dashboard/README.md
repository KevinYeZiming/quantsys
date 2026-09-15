# Quantsys 量化仪表盘

Quantsys 量化交易系统的可视化仪表盘：因子有效性评估 · 股/基/金统一买卖信号 · 持仓分析。

深色主题单页应用，React 19 + TypeScript + Vite + Tailwind CSS + shadcn/ui + Recharts。

| 总览 | 因子实验室 |
|---|---|
| ![overview](docs/screenshots/overview.png) | ![factor-lab](docs/screenshots/factor-lab.png) |

| 买卖信号 | 持仓 |
|---|---|
| ![signals](docs/screenshots/signals.png) | ![holdings](docs/screenshots/holdings.png) |

## 功能

- **总览**：因子数 / 信号统计 KPI、因子得分榜 TOP8、评级分布环图、最新买卖评估速览
- **因子实验室**：20 因子总表（RankIC · ICIR · 单调性 · A-D 评级）、日度 RankIC 时序、IC 衰减（1-20 日）、十分位分层收益、IC-ICIR 全景散点（含主流门槛参考线）、相关性热力图与冗余诊断
- **买卖信号**：每个标的的评分环 + 四维雷达（动量/趋势/风险/位置）、止损止盈参考、理由与风险标记、置信度与建议仓位
- **持仓**：成本/现价/浮动盈亏/评估总分/信号/建议仓位一览

## 快速开始

推荐方式：FastAPI 后端托管构建产物 + 一键更新接口（数据在运行时加载，更新后无需重新构建）：

```bash
cd dashboard
npm install
npm run build

cd ..
python3 scripts/serve_dashboard.py    # http://localhost:8000
```

打开页面后点击右上角「一键更新」按钮，即可自动完成：更新股票行情 → 更新基金数据 → 更新黄金数据 → 重新评估因子 → 重新生成买卖信号 → 刷新页面数据（实时显示每步进度）。

纯前端开发模式（需另开终端起后端以使用一键更新）：

```bash
npm install
npm run dev        # http://localhost:3000，/api 自动代理到 8000
```

```bash
npm run build      # 产物在 dist/（纯静态站点）
npm run preview    # 本地预览构建产物
```

## 数据从哪来

仪表盘本身不联网，数据来自运行时加载的 `data/dashboard.json`（构建时从 `public/` 拷贝到 `dist/`，一键更新后直接重写该文件），由系统脚本导出：

```bash
# 在项目根目录（dashboard 的上级目录）依次运行：
python3 scripts/evaluate_factors.py --start 2022-01-01 --save-weights   # 因子评估
python3 scripts/evaluate_assets.py --positions                          # 买卖评估
python3 scripts/export_dashboard_data.py                                # 导出 dashboard.json
```

点击「一键更新」即自动执行以上步骤外加行情抓取，无需手动操作。

## 部署到 GitHub Pages

`vite.config.ts` 已配置 `base: './'`（相对路径），构建产物可直接托管：

```bash
npm run build
# 将 dist/ 推到 gh-pages 分支，或使用 GitHub Actions 自动部署
```

## 目录结构

```
dashboard/
├── public/data/dashboard.json     # 运行时数据（由 export_dashboard_data.py 生成，构建时拷入 dist/）
├── src/
│   ├── sections/                  # 总览 / 因子实验室 / 买卖信号 / 持仓
│   ├── components/                # 更新按钮、相关性热力图等 + shadcn/ui
│   └── pages/Home.tsx             # 入口布局与导航（运行时 fetch 数据，支持 #hash 深链接）
├── docs/screenshots/              # 预览截图
└── index.html
```

## 免责声明

本仪表盘为量化研究工具的输出展示，不构成投资建议。
