---
title: "GitHub 拿走了按 workflow 统计的分钟数，怎么拿回来"
description: GitHub 按 workflow 查询 Actions 用量的接口正在下线，账单页只按 SKU 和仓库汇总。本文讲怎么用 runs 和 jobs API 还原每个 workflow、每个 job 的计费分钟和费用，以及做这件事的开源工具 runbill。
---

# GitHub 拿走了按 workflow 统计的分钟数，怎么拿回来

*2026 年 10 月 · [English](per-workflow-minutes.md)*

这个月 Actions 账单涨了。账单页会告诉你涨了多少，按仓库、按 runner 类型分好。但它不会告诉你是**哪个 workflow** 花的，更别说哪个 job，或者其中有多少是在反复重跑一个不稳定的测试直到变绿。

以前第一个问题有 API 可以查，现在它要没了。

## 发生了什么变化

**按 workflow 查用量的接口正在下线。** `GET /repos/{owner}/{repo}/actions/workflows/{workflow_id}/timing`（"Get workflow usage"）以及按单次运行查询的对应接口，随着账户迁移到 GitHub 新计费平台而[逐步关闭](https://github.blog/changelog/2025-02-02-actions-get-workflow-usage-and-get-workflow-run-usage-endpoints-closing-down/)。GitHub 的公告建议改用计费平台的 usage 接口，但原话是它"按 SKU、组织和仓库汇总 Actions 用量，不提供详细的 workflow 信息"。workflow 级别的信息现在只在账单页申请、通过邮件发送的用量报告里（[查看用量](https://docs.github.com/en/billing/how-tos/products/view-productlicense-use)）。

其实这个接口本来就不是账单口径。它自己的[文档](https://docs.github.com/en/rest/actions/workflows#get-workflow-usage)写明：用量"不包含 macOS 和 Windows runner 的倍率，也没有向上取整到整分钟"，而且只覆盖使用 GitHub 托管 runner 的私有仓库。job 级别的数据从来就没有。

**价格也变了。** 2026 年 1 月 1 日起，GitHub [将托管 runner 价格最多下调 39%](https://github.blog/changelog/2026-01-01-reduced-pricing-for-github-hosted-runners-usage/)。原定 2026 年 3 月 1 日对自托管 runner 收取的每分钟 $0.002"云平台费"已经[推迟](https://github.blog/changelog/2025-12-16-coming-soon-simpler-pricing-and-a-better-experience-for-github-actions/)（"以便重新评估方案"）。目前的[计费文档](https://docs.github.com/en/billing/concepts/product-billing/github-actions)仍然写着：自托管 runner，以及公开仓库使用标准托管 runner，都是免费的。

总结一下：单价便宜了，但分钟花在哪儿反而更难看清。

## GitHub 实际怎么给一个 job 计费

还原明细需要的规则都在 [runner 价格参考](https://docs.github.com/en/billing/reference/actions-runner-pricing)里：

1. **按 job 计、向上取整。** "GitHub 会把每个 job 使用的分钟和不足一分钟的部分向上取整到整分钟。"一个 10 秒的 lint job 也算 1 分钟；20 个很短的矩阵 job 至少算 20 分钟。
2. **按 runner 类型计价。** 每种 runner 有自己的每分钟单价。标准 runner 当前牌价：

    | Runner | 计费 SKU | 美元/分钟 |
    |---|---|---|
    | Linux 2 核（x64） | `actions_linux` | $0.006 |
    | Linux 2 核（arm64） | `actions_linux_arm` | $0.005 |
    | Windows 2 核（x64） | `actions_windows` | $0.010 |
    | macOS 3/4 核 | `actions_macos` | $0.062 |

    一分钟 macOS 约等于十分钟 Linux。大规格 runner 另有价目（例如 Linux 8 核 x64 为 $0.022）。
3. **重跑照样计费。** GitHub 自己举的例子：一个 workflow 跑了 5 分钟失败，修好后重跑 10 分钟成功，总共用掉 15 分钟（[计费文档](https://docs.github.com/en/billing/concepts/product-billing/github-actions#examples-of-how-usage-is-measured)）。
4. **哪些免费。** 公开仓库的标准托管 runner、自托管 runner，以及套餐内含的分钟数（GitHub Free 每月 2,000 分钟，Pro 和 Team 3,000 分钟，Enterprise Cloud 50,000 分钟）。大规格 runner 始终收费，公开仓库也不例外。

## 用 API 自己还原明细

普通的 Actions API 就够了，只需要 `actions:read` 权限：

- `GET /repos/{owner}/{repo}/actions/runs?created=>=YYYY-MM-DD` 列出运行记录，每条带 workflow 名称和 `run_attempt`。
- `GET /repos/{owner}/{repo}/actions/runs/{run_id}/jobs?filter=all` 列出每次尝试的所有 job，带 `started_at`、`completed_at`、`labels` 和 `run_attempt`。

对每个 job：用 `completed_at - started_at`，向上取整到整分钟，按 runner 标签选单价（`macos-14` → macOS，`windows-latest` → Windows，`ubuntu-24.04-arm` → Linux arm64，`self-hosted` → $0），再累加到所属 workflow 和 job 名下。第 2 次及以后的尝试就是重跑，单独汇总。被 skipped 的 job 跳过。

思路就这么简单。麻烦的是分页、`filter=all`（不加只能看到最近一次尝试）、各种标签写法，还有别忘了公开仓库实际账单是 0。

## runbill：一条命令做完这些

[runbill](https://github.com/Blackman99/runbill) 就是把上面这套逻辑打包好了：纯 Python 标准库的命令行工具，同时也是一个 GitHub Action。它读取 `GH_TOKEN` / `GITHUB_TOKEN`，或者直接用你的 `gh` 登录。

```bash
pipx install git+https://github.com/Blackman99/runbill
runbill 你的组织/仓库 --days 30
```

下面是对 [astral-sh/uv](https://github.com/astral-sh/uv) 的一次真实运行，只取最新的 80 次运行：

```console
$ runbill astral-sh/uv --days 2 --max-runs 80 --top 6
runbill: fetching jobs for 80 runs…
runbill · astral-sh/uv · runs since 2026-10-08 (80 runs, 2100 jobs)

  TOTAL          9,272 billed min      $134.83   (raw 8,055 min, re-runs 17.6%)

  BY WORKFLOW                              runs    billed min        cost   share
  CI                                          18         5,666      $59.50   44.1%
  Debug study calibration block 0              2           497      $13.48   10.0%
  Debug study calibration block 1              2           495      $13.35    9.9%
  Debug study confirmatory block 1002          1           421       $7.92    5.9%
  Debug study confirmatory block 1001          1           411       $7.92    5.9%
  Debug study confirmatory block 1003          1           409       $7.90    5.9%

  TOP 6 JOBS                               jobs    billed min        cost
  Debug study calibration block 0 › macOS      2           180      $11.16
  Debug study calibration block 1 › macOS      2           178      $11.04
  CI › build-release-artifacts / aarch64-a     8            96       $5.95
  Debug study confirmatory block 1001 › ma     1            90       $5.58
  Debug study confirmatory block 1003 › ma     1            90       $5.58
  Debug study confirmatory block 1005 › ma     1            90       $5.58

  ! stopped at --max-runs; totals cover only the newest runs.
  Public repo: standard GitHub-hosted runners are free here. Figures show what these minutes would cost at list price on a private repo.
```

uv 是公开仓库，这些分钟对他们是免费的；费用一列是同样的运行放在私有仓库、按牌价要花多少钱。有三点是账单页永远看不出来的：

- **CI 只占 44%，不是 100%。** 这段时间里一半以上的牌价费用来自几个一次性的 "Debug study" workflow。
- **最贵的 job 是 macOS job。** 排名前两位的 job 共 358 计费分钟、$22.20，约占总额的六分之一，原因就是 macOS 的单价。
- **17.6% 的费用来自重跑**（第 2 次及以后的尝试）。

取整对又短又快的 job 影响最大。runbill 自己的仓库，最近 7 天：

```console
$ runbill Blackman99/runbill --days 7 --top 3
runbill: fetching jobs for 3 runs…
runbill · Blackman99/runbill · runs since 2026-10-03 (3 runs, 13 jobs)

  TOTAL             13 billed min        $0.14   (raw 3 min, re-runs 0.0%)

  BY WORKFLOW                              runs    billed min        cost   share
  CI                                           1            10       $0.12   87.0%
  Pages                                        1             2       $0.01    8.7%
  Release                                      1             1       $0.01    4.3%

  TOP 3 JOBS                               jobs    billed min        cost
  CI › test (macos-latest, py3.12)             1             1       $0.06
  CI › test (windows-latest, py3.12)           1             1       $0.01
  CI › build                                   1             1       $0.01

  Public repo: standard GitHub-hosted runners are free here. Figures show what these minutes would cost at list price on a private repo.
```

13 个 job 合计实际运行约 3 分钟，却计费 13 分钟，因为每个 job 都单独向上取整。如果私有仓库里有一大堆很快跑完的矩阵 job，这个差距就是真金白银。

其他常用参数：`--workflow ci.yml`、`--branch main`、`--format md|json|csv`、用 `--rate macos=0.08` 覆盖单价，以及 `--fail-over 50`：估算超过 $50 时以退出码 3 结束。

## 在 CI 里每周跑一次

作为 Action 使用时，它会把报告写进 job summary，还可以设预算门槛：

```yaml
name: Actions minutes
on:
  schedule: [{ cron: "0 1 * * 1" }]   # 每周一
  workflow_dispatch:
permissions: { actions: read, contents: read }
jobs:
  meter:
    runs-on: ubuntu-latest
    steps:
      - uses: Blackman99/runbill@v0.1.0
        with: { days: 7, fail-over: 20 }
```

## 它不是什么

runbill 给的是**按牌价的估算**，不是对账。它不知道你套餐里的免费分钟、折扣或合同价。大规格 runner 按 GitHub [公布的分规格单价](https://docs.github.com/en/billing/reference/actions-runner-pricing)计价（Linux 8 核 $0.022/分钟，macOS `xlarge` $0.102，单核 `ubuntu-slim` $0.002），但大规格 runner 的标签由组织管理员自己命名，只有标签里带核数（`…-8-cores`）或 macOS 的 `large`/`xlarge` 后缀时，runbill 才能识别规格。要权威的按 workflow 数字，还是看账单页的用量报告；runbill 的用途是在终端或定时任务里找出分钟**花在哪儿**，细到 job 和重跑。

[路线图](https://github.com/Blackman99/runbill/blob/main/ROADMAP.md)上的下一步：组织级汇总（`runbill org ORG`）、按分支和触发事件拆分，以及周环比 `--compare`。

欢迎在 [issues](https://github.com/Blackman99/runbill/issues) 反馈，尤其是 runbill 识别错的 runner 标签配置。

## 参考来源

- GitHub Changelog，[Actions Get workflow usage and Get workflow run usage endpoints closing down](https://github.blog/changelog/2025-02-02-actions-get-workflow-usage-and-get-workflow-run-usage-endpoints-closing-down/)（2025-02-02）
- GitHub REST 文档，[Get workflow usage](https://docs.github.com/en/rest/actions/workflows#get-workflow-usage)
- GitHub Changelog，[Reduced pricing for GitHub-hosted runners usage](https://github.blog/changelog/2026-01-01-reduced-pricing-for-github-hosted-runners-usage/)（2026-01-01）
- GitHub Changelog，[Update to GitHub Actions pricing](https://github.blog/changelog/2025-12-16-coming-soon-simpler-pricing-and-a-better-experience-for-github-actions/)（2025-12-16，自托管收费推迟）
- GitHub 文档，[GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- GitHub 文档，[Actions runner pricing](https://docs.github.com/en/billing/reference/actions-runner-pricing)
- GitHub 文档，[Viewing usage of metered products](https://docs.github.com/en/billing/how-tos/products/view-productlicense-use)
