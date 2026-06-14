# 六合彩分析工具

基于历史开奖数据的六合彩统计分析工具，支持 **香港 / 老澳门 / 新澳门** 三种彩种。

## 脚本一览

| 文件 | 说明 |
|------|------|
| [lhc_analyzer.py](./lhc_analyzer.py) | 命令行分析脚本（核心引擎） |
| [lhc_gui.py](./lhc_gui.py) | Windows 图形界面（可调权重） |
| [run_gui.bat](./run_gui.bat) | 双击启动 GUI |
| [requirements.txt](./requirements.txt) | Python 依赖 |

## 快速开始

```powershell
cd scripts
pip install -r requirements.txt
python lhc_gui.py
```

## 详细教程

请阅读 **[使用教程.md](./使用教程.md)**，包含：

- 各脚本用途说明
- Windows 安装步骤
- 图形界面与命令行完整用法
- 策略权重调参指南
- 常见问题解答

## 免责声明

历史统计不能预测未来开奖结果，输出仅供娱乐参考，请理性购彩。
