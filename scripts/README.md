# 六合彩分析工具

基于历史开奖数据的六合彩统计分析工具，支持 **香港 / 老澳门 / 新澳门** 三种彩种。

## 脚本一览

| 文件 | 说明 | 平台 |
|------|------|------|
| [lhc_analyzer.py](./lhc_analyzer.py) | 命令行分析脚本（核心引擎） | 全平台 |
| [lhc_gui.py](./lhc_gui.py) | 图形界面（可调权重） | Windows / macOS / Linux |
| [run_gui.bat](./run_gui.bat) | 双击启动 GUI | Windows |
| [run_gui.sh](./run_gui.sh) | 终端启动 GUI | macOS / Linux |
| [run_gui.command](./run_gui.command) | Finder 双击启动 | macOS |
| [lhc_zodiac.py](./lhc_zodiac.py) | 生肖映射与统计分析（自动集成） | 全平台 |

## 快速开始

**Windows**

```powershell
cd scripts
pip install -r requirements.txt
python lhc_gui.py
```

**macOS**

```bash
cd scripts
python3 -m pip install -r requirements.txt
chmod +x run_gui.sh run_gui.command
./run_gui.sh
```

## 详细教程

请阅读 **[使用教程.md](./使用教程.md)**，包含 Windows / macOS 安装步骤、GUI 与 CLI 用法、权重调参及 FAQ。

## 免责声明

历史统计不能预测未来开奖结果，输出仅供娱乐参考，请理性购彩。
