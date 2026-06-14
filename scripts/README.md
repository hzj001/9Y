# 六合彩分析工具

基于历史开奖数据的六合彩统计分析工具，支持 **香港六合彩 / 老澳门六合彩 / 新澳门六合彩** 三种彩种。

提供 **图形界面** 与 **命令行** 两种使用方式，集成号码分析、生肖分析、权重调参、JSON 导出等功能。

> **免责声明**：六合彩开奖在理论上各号码概率相等，历史统计**不能预测**未来结果。本工具输出仅供数据分析与娱乐参考，请理性购彩。

---

## 功能特性

| 功能 | 说明 |
|------|------|
| 多彩种支持 | 香港（xg6）、老澳门（am6）、新澳门（nam6），可一次分析全部 |
| 号码分析 | 推荐正码 Top N、推荐特码、正码/特码/综合排名 |
| 生肖分析 | 号码对照表、历史出现比例、最新期分布、下一期生肖参考 |
| 策略权重 | 6 维加权打分（全频、近热、正码、特码、遗漏、周期），GUI 滑块可调 |
| 本地缓存 | 历史数据缓存至 `data/`，支持离线重复分析 |
| 图形界面 | 分标签页展示：综合摘要 / 号码分析 / 生肖分析 / 完整报告 |
| JSON 导出 | GUI 一键导出结构化结果，CLI 支持 `--json` |
| 跨平台 | Windows / macOS / Linux |

---

## 目录结构

```
scripts/
├── lhc_analyzer.py      # 核心分析引擎（命令行）
├── lhc_gui.py           # 图形界面（推荐日常使用）
├── lhc_zodiac.py        # 生肖映射与统计（被上述脚本自动调用）
├── run_gui.bat          # Windows 双击启动
├── run_gui.sh           # macOS / Linux 终端启动
├── run_gui.command      # macOS Finder 双击启动
├── requirements.txt     # Python 依赖（requests）
├── README.md            # 本文档
├── 使用教程.md           # 详细教程（安装、参数、FAQ）
└── data/                # 本地缓存（运行后自动生成，已 gitignore）
    ├── xg6_history.json
    ├── am6_history.json
    └── nam6_history.json
```

---

## 环境要求

- **Python 3.10+**
- **requests**（`pip install -r requirements.txt`）
- **tkinter**（图形界面需要；python.org 官方安装包自带；Homebrew 需 `brew install python-tk@3.12`）

---

## 快速开始

### 1. 获取代码

```bash
git clone https://github.com/hzj001/9Y.git
cd 9Y/scripts
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
# macOS 建议：python3 -m pip install -r requirements.txt
```

### 3. 启动图形界面（推荐）

**Windows**

```powershell
python lhc_gui.py
# 或双击 run_gui.bat
```

**macOS**

```bash
chmod +x run_gui.sh run_gui.command
./run_gui.sh
# 或在 Finder 中双击 run_gui.command
```

**Linux**

```bash
chmod +x run_gui.sh
./run_gui.sh
```

### 4. 命令行快速分析

```bash
# 新澳门，最近 200 期，写入缓存
python lhc_analyzer.py -t 新澳门 --cache --limit 200

# 三个彩种一起分析
python lhc_analyzer.py -t all --cache --limit 200

# JSON 输出
python lhc_analyzer.py -t 新澳门 --json --limit 200
```

---

## 图形界面说明

左侧为 **分析设置**，右侧为 **结果标签页**：

| 标签页 | 内容 |
|--------|------|
| 综合摘要 | 推荐正码、特码、生肖 Top 5、比例概览 |
| 号码分析 | 正码/特码强度排名、策略得分 |
| 生肖分析 | 对照表、出现比例、下一期生肖参考 |
| 完整报告 | 与命令行输出一致的全文 |

### 左侧可调参数

| 参数 | 说明 | 默认 |
|------|------|------|
| 彩种 | 香港 / 老澳门 / 新澳门 / 全部 | 新澳门 |
| 分析期数 | 使用最近 N 期；填 `0` 表示全部 | 200 |
| 近期窗口 | 「近期热度」统计范围（期数） | 30 |
| 推荐正码数 | 推荐正码个数 | 6 |
| 特码 Top N | 展示特码排名前 N | 3 |
| 策略权重 | 6 个滑块，分析时自动归一化 | 见下表 |
| 写入本地缓存 | 保存至 `data/{彩种}_history.json` | 开启 |
| 强制刷新 | 忽略缓存，重新从 API 拉取 | 关闭 |

### 策略权重（默认）

| 策略 | 权重 | 含义 |
|------|------|------|
| 全历史频率 | 20% | 长期出现次数 |
| 近期热度 | 25% | 最近 N 期表现 |
| 正码强度 | 20% | 作为正码出现的频率 |
| 特码强度 | 10% | 作为特码出现的频率 |
| 遗漏期数 | 15% | 越久未出，分越高 |
| 出现周期 | 10% | 平均间隔越短，分越高 |

权重同时作用于 **号码** 与 **生肖** 推荐排序。

---

## 命令行参数

```
usage: lhc_analyzer.py [-h] [-t TYPE] [--limit N] [--recent N]
                       [--top-regular N] [--top-special N]
                       [--cache] [--refresh] [--json] [--weights ...]

常用参数：
  -t, --type          彩种：xg6 / am6 / nam6 / all，或中文「香港」「老澳门」「新澳门」
  --limit             只分析最近 N 期（默认全部）
  --recent            近期热度窗口，默认 30
  --top-regular       推荐正码数，默认 6
  --top-special       特码 Top N，默认 3
  --cache             拉取后写入本地缓存
  --refresh           忽略缓存，强制更新
  --json              JSON 格式输出
  --weights           自定义权重，如 frequency:0.3,recent_hot:0.3,...
```

### 示例

```bash
# 老澳门，强制刷新全部历史
python lhc_analyzer.py -t 老澳门 --cache --refresh

# 偏重近期热度
python lhc_analyzer.py -t 香港 --weights "frequency:0.10,recent_hot:0.40,regular_strength:0.20,special_strength:0.10,overdue:0.10,gap_cycle:0.10"
```

---

## 生肖分析说明

- 按 **农历年** 映射 1–49 号码到 12 生肖（01=本命生肖，如 2026 马年：01/13/25/37/49 为马）
- **实际比例** = 出现次数 ÷ (期数 × 7)
- **理论比例** = 该生肖号码数 ÷ 49（本命年约 10.2%，其余约 8.2%）
- 跨年历史数据按期开奖日期的农历年分别映射，保证统计准确

---

## 支持的彩种

| 代码 | 名称 | CLI 示例 |
|------|------|----------|
| `xg6` | 香港六合彩 | `-t 香港` |
| `am6` | 老澳门六合彩 | `-t 老澳门` |
| `nam6` | 新澳门六合彩 | `-t 新澳门` |
| `all` | 三个一起分析 | `-t all` |

---

## 常见问题

### `pip install -r requirements.txt` 找不到文件

注意当前目录：

| 所在目录 | 正确命令 |
|----------|----------|
| `9Y/scripts` | `pip install -r requirements.txt` |
| `9Y`（根目录） | `pip install -r scripts/requirements.txt` |

### `No module named 'tkinter'`

| 系统 | 解决方法 |
|------|----------|
| Windows | 重装 Python，勾选 **tcl/tk and IDLE** |
| macOS (Homebrew) | `brew install python-tk@3.12` |
| macOS (推荐) | 使用 [python.org](https://www.python.org/downloads/) 官方 pkg |
| Linux | `sudo apt install python3-tk` |

也可只用命令行：`python lhc_analyzer.py`（不依赖 tkinter）。

### `git pull` 连接 GitHub 失败

网络问题时可：
1. 使用代理后再 `git pull`
2. 或浏览器打开 https://github.com/hzj001/9Y → **Code → Download ZIP**，覆盖 `scripts` 文件夹

### 网络/API 超时

```bash
# 先用本地缓存分析（不加 --refresh）
python lhc_analyzer.py -t 新澳门 --limit 200
```

---

## 脚本关系

```
run_gui.bat / run_gui.sh / run_gui.command
                    │
                    ▼
              lhc_gui.py ──────► 综合摘要 / 号码 / 生肖 / 导出
                    │
                    ▼
            lhc_analyzer.py ────► 数据拉取 · 号码统计 · CLI
                    │
                    ▼
              lhc_zodiac.py ────► 生肖映射 · 比例 · 下一期参考
                    │
                    ▼
           公开 API + data/*.json 缓存
```

---

## 详细教程

更完整的安装步骤、界面截图说明、调参建议与 FAQ，请参阅：

**[使用教程.md](./使用教程.md)**

---

## 许可证与免责

本工具仅供学习、数据统计与娱乐参考。使用者须自行承担购彩风险，开发者不对任何投注损失负责。

历史统计结果**不代表**未来开奖概率，请勿将推荐号码或生肖作为购彩依据。
