# 9Y

本仓库包含 Android 项目配置，以及 `scripts/` 目录下的 **六合彩分析工具**。

## 六合彩分析工具

基于历史开奖数据的统计分析工具，支持香港 / 老澳门 / 新澳门三种彩种，提供图形界面与命令行两种使用方式。

**主要功能：**

- 号码推荐（正码 / 特码 / 综合排名）
- 生肖分析（对照表、出现比例、下一期参考）
- 策略权重可调（GUI 滑块 / CLI 参数）
- 本地缓存、JSON 导出

### 快速开始

```bash
cd scripts
pip install -r requirements.txt
python lhc_gui.py          # 图形界面（推荐）
# python lhc_analyzer.py -t 新澳门 --cache --limit 200   # 命令行
```

| 平台 | 启动方式 |
|------|----------|
| Windows | `python lhc_gui.py` 或双击 `scripts/run_gui.bat` |
| macOS | `./scripts/run_gui.sh` 或双击 `scripts/run_gui.command` |
| Linux | `./scripts/run_gui.sh` |

### 文档

- **[scripts/README.md](./scripts/README.md)** — 功能说明、参数、FAQ
- **[scripts/使用教程.md](./scripts/使用教程.md)** — 详细安装与使用教程

> 历史统计不能预测未来开奖结果，输出仅供娱乐参考，请理性购彩。

## Android 项目

根目录为 Android / Gradle 工程配置，`app/` 模块见本地工程结构。
