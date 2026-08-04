# E2E 测试集（真实网络）

BiliMuse 落地验收测试：真实网络下载链路，YAML 用例驱动，带「标准答案」（机器校验）与「人工评审」（主观项）。

## 组成

| 文件 | 说明 |
|---|---|
| `cases.yaml` | 35 条用例定义：搜索/下载/格式/边界/校准专项/三端 |
| `run_testset.py` | 主运行器：逐条走搜索→下载→打标签→配歌词→校准，自动校验 expect |
| `align_bench.py` | 校准基准：whisper 对齐 vs `gold/` 人工标注时间戳，算中位误差 |
| `gold/` | 5 首人工标注标准时间戳（json） |
| `dl/` | 运行时下载产物（gitignore，不入库） |
| `report/` | 报告输出 report.md + report.json（gitignore） |

## 运行

```bash
# 全套
python tests/e2e/run_testset.py

# 常用参数
python tests/e2e/run_testset.py --only C01,C05     # 只跑指定用例
python tests/e2e/run_testset.py --no-align         # 关 whisper 校准（快速冒烟）
python tests/e2e/run_testset.py --config-dir <dir> # 用临时配置目录隔离运行（默认读真实配置）
python tests/e2e/run_testset.py --download-dir tests/e2e/dl
python tests/e2e/run_testset.py --out report/full.md

# 校准基准
python tests/e2e/align_bench.py
```

> 配置隔离：`--config-dir` 指向一个含 `config.json` 的临时目录（需含 sessdata 与 whisper_model），避免污染真实配置/下载历史。sessdata 可从 `bilimuse config` 或现有配置复制。

## 标准答案双轨

- **机器校验**（`expect`）：搜索成员命中、文件存在、标签回读、时长容差、语言、歌词关键词、来源、校准方法 → PASS/FAIL
- **人工评审**（`review`）：报告生成评审表（歌词行 vs whisper 时间戳），按 A/B/C 打分后汇总

## 用例矩阵（35 条）

| 组 | id | 覆盖 |
|---|---|---|
| 中文经典 | C01-C05 | 晴天/七里香/搁浅/以父之名/双截棍 |
| 歌词片段反查 | C06-C09 | 中/英/日片段→歌名 |
| 日语 | C10-C13 | One Last Kiss/Beautiful World/冷门/无人声 |
| 英文 | C14-C16 | 经典/翻唱/快歌 |
| 粤语·韩语 | C17-C20 | 语言检测/翻唱 |
| 格式 | C21-C23 | m4a/mp3/flac(降级) |
| 边界异常 | C24-C29 | 无歌词占位/多P/去重/脏字符/极短/无结果 |
| 校准专项 | C30-C34 | gold 基准 5 首 |
| 三端 | C35 | Web API + WS 下载事件流 |

## 判定标准（校准基准）

- 中位误差 ≤ 1.5s：优；≤ 3.0s：通过；> 3.0s：失败
