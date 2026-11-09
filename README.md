# 五子棋 Gomoku

Python + Pygame 的桌面五子棋，内置神经网络 MCTS AI。克隆下来装好 pygame 就能开玩，不需要另外下载模型。

## 快速开始

环境：Windows（AI 求解器是 `.exe`）、Python 3.8+。

```bash
pip install -r requirements-game.txt
python main.py
```

AI 相关文件已经放在 `src/v2/` 里（求解器 + 模型 + ONNX Runtime），无需额外配置。

## 玩法

- 主菜单：人 vs 人 / 人 vs 机 / 观看回放，可切换中英文
- 人 vs 机支持选择执黑或执白
- 左键落子，`Ctrl+Z` 悔棋，`ESC` 打开暂停菜单
- 人机对战按 `H` 或点右下角「提示」，查看 AI 推荐落点、当前胜率和 top5 候选
- 每局结束自动保存棋谱到 `records/`（JSON），可从「观看回放」再次打开

## 目录

```
main.py               程序入口
game/                 界面、棋盘、棋谱、回放、求解器桥接
src/v0/               启发式 MCTS 求解器（C++，零依赖）
src/v1/               早期神经网络 MCTS 求解器（C++ + ONNX Runtime）
src/v2/               神经网络 MCTS 求解器（C++ + ONNX Runtime），默认使用
PROTOCOL.md           游戏与求解器的通信协议
requirements-game.txt 运行依赖（pygame）
setup.bat             PyInstaller 打包脚本
records/              对局棋谱输出目录（运行后生成）
```

## AI 版本

三代求解器，默认使用 v2：

| 版本 | 做法 | 说明 |
|---|---|---|
| v0 | 启发式 MCTS，随机 rollout，零依赖 | 兜底；v2 缺失或启动失败时自动回退 |
| v1 | 早期神经网络（约 43 万参数）+ MCTS | 已被 v2 取代，仅作对照 |
| v2 | KataGomo 蒸馏的 b6c96 网络（约 97 万参数）+ MCTS | **默认内置** |

替换成自己构建的版本：运行对应目录的 `build.bat`（v0 只需要 g++，v1 / v2 还需要 ONNX Runtime 的头文件和库），把生成的 `solver.exe` 放进 `src/vN/` 覆盖即可；v1 / v2 还需要同目录下配套的 `model.onnx` 与 `onnxruntime.dll`。

也可以完全自己实现一个求解器——只要按 [PROTOCOL.md](PROTOCOL.md) 通过 stdin/stdout 一问一答，游戏侧不需要任何改动。

## 通信协议

`solver.exe` 作为独立子进程运行：启动先输出 `READY` 握手，游戏发送 `search ...`，求解器回 `MOVE` / `INFO` / `TOP` / `END`。字段、坐标约定、错误码见 [PROTOCOL.md](PROTOCOL.md)。

## 打包

```bash
setup.bat
```

使用 PyInstaller 打包，产物在 `dist/Gomoku/`。

## 说明

- 仓库只保留可玩所需的部分：训练代码、技术报告等不在其中。
- 目前只提供 Windows 求解器；其他平台可以玩人 vs 人，或按协议自行实现 AI。
