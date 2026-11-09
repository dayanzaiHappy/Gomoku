# 五子棋求解器协议 v1

> 适用对象：`src/v0`、`src/v2`，以及任何第三方求解器实现。
> 本文只规定「怎么通信」，不规定搜索算法；模型张量约定见附录 A。

---

## 1. 术语

| 术语 | 含义 |
|---|---|
| solver | 一个独立的求解器进程，内部可以是指发式 MCTS、神经网络 MCTS 或任何其他实现 |
| client | 调用 solver 的一方，例如游戏、调试工具、对打评测器 |
| frame | 一次完整的请求或响应；响应以 `END` 行结束 |
| 走子方 | 当前轮到落子的一方，`1` = 黑，`2` = 白 |

一个 solver 进程只服务一个引擎 + 一个模型。需要同时跑多个版本时，开多个进程。

---

## 2. 传输层

| 项 | 约定 |
|---|---|
| 通道 | stdin / stdout |
| 编码 | ASCII |
| 换行 | 发送端使用 `\n`；接收端必须容忍 `\r\n` |
| stdout | **只允许出现协议内容**；日志、调试输出、ONNX Runtime 日志一律走 stderr |
| 刷新 | 每写完一个 `END` 必须立即 flush |
| 并发 | 严格一问一答；上一条响应未以 `END` 结束前，不得发送下一条请求 |
| 行长度 | 单行不超过 8192 字节 |
| 大小写 | 命令与 key 区分大小写，固定小写 |
| 生命周期 | 收到 EOF 或 `quit` 后退出；正常退出码 0 |

---

## 3. 坐标系与棋盘编码

- 棋盘 15×15
- `row` 0..14，从上到下；`col` 0..14，从左到右
- 线性下标 `index = row * 15 + col`
- 格子值：`0` 空、`1` 黑、`2` 白
- 请求里的 225 个格子值按 `index` 升序排列
- `player`：`1` 黑、`2` 白

`value` 一律表示**从走子方视角**的期望得分，范围 `[0, 1]`，和棋按 `0.5` 计。

---

## 4. 启动握手

solver 启动后必须先输出一行握手，再进入请求循环：

```text
READY <engine> <version> <protocol> sims_default=<int> [opt=<capabilities>]
END
```

| 字段 | 说明 |
|---|---|
| `engine` | 自由 token，不含空格，例如 `heuristic`、`nn` |
| `version` | 自由 token，例如 `v0`、`v2` |
| `protocol` | 固定整数 `1` |
| `sims_default` | `sims=0` 时实际使用的迭代次数 |
| `opt` | 可选能力列表，逗号分隔；当前定义 `noise`（支持根噪声 `alpha`/`eps`）和 `tau`（支持 `tau` 采样与 `SAMPLE` 行）。不声明表示不支持 |

示例：

```text
READY heuristic v0 1 sims_default=100000 opt=tau
END
```

```text
READY nn v2 1 sims_default=256 opt=noise,tau
END
```

初始化失败（模型缺失、加载失败等）：

```text
ERROR 202 model_load_failed
END
```

然后以非 0 退出码结束进程。

client 必须读到握手的 `END` 之后，才能发送第一条请求。

---

## 5. 搜索请求

```text
search <player> <sims> <max_ms> <topk> <c0> <c1> ... <c224> [alpha=<float>] [eps=<float>] [tau=<float>]
```

| 字段 | 取值 | 说明 |
|---|---|---|
| `player` | `1` / `2` | 走子方 |
| `sims` | `0 .. 10000000` | 搜索迭代次数；`0` = 使用握手里的 `sims_default` |
| `max_ms` | `0 .. 10000000` | 软时间上限，单位毫秒；`0` = 不限 |
| `topk` | `0 .. 64` | 需要返回的候选着法数量；`0` = 不返回候选 |
| `c0 .. c224` | `0` / `1` / `2` | 225 个格子值，按 `index` 升序 |

补充规则：

- 合法着法集合由 solver 内部决定（例如邻域半径），协议不规定
- 空棋盘：合法着法固定为 `[(7, 7)]`
- `sims=0` 时使用握手声明的 `sims_default`；`INFO sims` 返回实际完成的迭代数
- `sims` 与 `max_ms` 同时生效，先到先停
- 即使时间已到，也至少完成 1 次迭代
- 单次请求不保留任何跨请求状态（不做树复用）；同一个进程可以连续服务任意多局

### 5.1 随机化选项

三个选项只能出现在 225 个格子值之后，顺序任意；不出现时保持旧行为。

| 选项 | 默认 | 取值范围 | 说明 |
|---|---|---|---|
| `alpha` | `0.1` | `> 0` | Dirichlet 浓度；仅 `eps > 0` 时生效 |
| `eps` | `0` | `[0, 1]` | 根节点先验噪声混合系数；`0` = 关闭 |
| `tau` | `0` | `>= 0` | `0` = 不采样；`> 0` = 按 `visits^(1/tau)` 采样并输出 `SAMPLE` |

噪声规则：

- 只在根节点、只在合法着法的先验归一化之后施加一次：`p' = (1 - eps) * p + eps * Dir(alpha)`
- 合法着法数小于 2 时不施加

采样规则：

- 候选集 = 根节点中 `visits > 0` 的子节点，按 §6.4 排序
- `topk > 0`：取前 `min(topk, 候选数)` 个；`topk = 0`：使用全部候选
- 采样概率 ∝ `visits^(1 / tau)`，在候选集内重新归一化
- 无合法着法时不采样、不输出 `SAMPLE`

选项只影响当前请求；服务端不得跨请求保留随机数状态。

---

## 6. 搜索响应

```text
MOVE <row> <col>
INFO time_ms=<int> sims=<int> value=<float> legal=<int> stopped=<sims|time|no_move>
[TOP <row> <col> visits=<int> value=<float>
 ...]
END
```

### 6.1 行顺序

1. `MOVE` 必须是第一行
2. `INFO` 必须紧随其后，且只出现一次
3. `SAMPLE` 可选，最多一行，位置在 `INFO` 之后、`TOP` 之前
4. `TOP` 可以出现 0 行或多行
5. 最后一行必须是 `END`

### 6.2 `MOVE`

- `MOVE <row> <col>`：最佳着法
- 无合法着法：`MOVE -1 -1`
- 最佳着法定义：根节点 `visits` 最多者；并列时取 `value` 更高者；再并列取 `index` 更小者

### 6.3 `INFO`

固定字段，顺序固定：

| 字段 | 类型 | 说明 |
|---|---|---|
| `time_ms` | int | 本次搜索耗时（毫秒），从解析完请求开始计 |
| `sims` | int | 实际完成的迭代次数 |
| `value` | float | 根节点走子方视角期望得分；无合法着法时为 `-1.000000` |
| `legal` | int | 合法着法数量 |
| `stopped` | enum | `sims` / `time` / `no_move` |

`stopped` 取值：

- `sims`：完成了请求的迭代数
- `time`：`max_ms` 先到，提前停止
- `no_move`：没有合法着法，未执行搜索

浮点数统一输出 6 位小数。

### 6.4 `TOP`

仅当 `topk > 0` 时出现。

```text
TOP <row> <col> visits=<int> value=<float>
```

- 只输出**根节点中 visits > 0 的子节点**
- 数量 = `min(topk, visits>0 的子节点数)`
- 排序：`visits` 降序 → `value` 降序 → `index` 升序
- `value` 已翻转为**根走子方视角**：走完该着后，从当前走子方看，越高越好

### 6.5 无着法

```text
MOVE -1 -1
INFO time_ms=0 sims=0 value=-1.000000 legal=0 stopped=no_move
END
```

无着法时不输出 `SAMPLE` 和 `TOP`。

### 6.6 `SAMPLE`

仅当请求的 `tau > 0` 且存在合法着法时出现，最多一行：

```text
SAMPLE <row> <col>
```

- 这是按 §5.1 规则采样得到的着法，供随机对弈模式使用
- `MOVE` 仍是 §6.2 定义的最佳着法，不受 `tau` 影响
- 客户端可以忽略本行，继续使用 `MOVE`（向前兼容）
- 无着法时不输出 `SAMPLE`

---

## 7. 错误

```text
ERROR <code> <message>
END
```

- `message` 为单行 ASCII，最长 200 字符，不含换行
- 1xx：请求级错误，回复后进程继续服务
- 2xx：进程级错误，回复后退出

| code | 含义 | 类别 |
|---|---|---|
| 100 | 解析失败 / 未知命令 | 可恢复 |
| 101 | 棋盘非法（数量不为 225、格子值越界） | 可恢复 |
| 102 | `player` 非法 | 可恢复 |
| 103 | 参数越界（`sims` / `max_ms` / `topk` / `alpha` / `eps` / `tau`） | 可恢复 |
| 104 | 未知请求选项 | 可恢复 |
| 200 | 内部错误 | 致命 |
| 201 | 推理失败（NaN / 模型执行错误） | 致命 |
| 202 | 模型缺失 / 加载失败（启动阶段） | 致命 |

示例：

```text
ERROR 103 topk_out_of_range
END
```

---

## 8. 控制命令

| 请求 | 响应 | 说明 |
|---|---|---|
| `ping` | `PONG` + `END` | 健康检查 |
| `quit` | `OK` + `END` | 回复后以退出码 0 结束 |
| 其他 | `ERROR 100 unknown_command` + `END` | 进程继续 |

---

## 9. 客户端义务

1. 读到握手 `END` 后才发请求
2. 每条请求后必须读到 `END`，即使只关心 `MOVE`
3. 必须忽略不认识的 `INFO` / `TOP` key，以及不认识的中间行类型（向前兼容）
4. 读超时：`max_ms > 0 ? max_ms + 5000 : 60000` 毫秒；超时后 kill 进程并按需重启
5. `quit` 后最多等待 500 ms，再强杀
6. 同一进程同一时间只允许一条未完成请求
7. 不要向已经终止的进程继续写请求
8. `sims=0` 时以握手的 `sims_default` 为准；对打/评测必须显式传 `sims`，避免不同引擎的默认值不可比
9. 必须先检查 READY 的 `opt` 能力位，只发送被支持的请求选项
10. 必须忽略不认识的中间行类型（包括 `SAMPLE`）

---

## 10. 服务端义务

1. 握手必须最先输出，且在模型加载完成后输出
2. stdout 不得出现任何协议之外的内容
3. 每条请求必须恰好回复一个 frame，且以 `END` 结束
4. 每写完 `END` 立即 flush
5. 请求级错误（1xx）不得退出进程
6. `MOVE` / `TOP` 的排序规则必须与第 6 节一致；`eps=0` 且 `tau=0` 时同一请求应逐字节可复现，开启随机化时不保证逐字节复现，但排序规则不变
7. `value` 的视角必须始终是根节点走子方
8. 不得在请求之间保留影响结果的搜索状态；随机数生成器必须按请求创建或按请求播种，不得跨请求推进

---

## 11. 示例

> 示例中的 225 个格子值用 `0 ... 0` 缩写，实际通信时必须完整给出 225 个整数。

### 11.1 正常落子（topk=0）

```text
> search 1 256 0 0 0 ... 0
< MOVE 7 7
< INFO time_ms=1420 sims=256 value=0.610300 legal=8 stopped=sims
< END
```

### 11.2 提示（topk=5）

```text
> search 1 256 0 5 0 0 0 ... 0
< MOVE 7 7
< INFO time_ms=1441 sims=256 value=0.610300 legal=8 stopped=sims
< TOP 7 7 visits=96 value=0.610300
< TOP 8 7 visits=41 value=0.587100
< TOP 6 7 visits=27 value=0.576400
< TOP 7 8 visits=18 value=0.552200
< TOP 6 6 visits=11 value=0.541000
< END
```

### 11.3 无着法

```text
> search 2 256 0 5 1 1 1 ... 2
< MOVE -1 -1
< INFO time_ms=0 sims=0 value=-1.000000 legal=0 stopped=no_move
< END
```

### 11.4 参数错误

```text
> search 1 256 0 65 0 0 ... 0
< ERROR 103 topk_out_of_range
< END
```

### 11.5 健康检查与退出

```text
> ping
< PONG
< END
> quit
< OK
< END
```

### 11.6 随机对弈（topk=3，alpha=0.1，eps=0.25，tau=0.6）

```text
> search 1 256 0 3 0 ... 0 alpha=0.100000 eps=0.250000 tau=0.600000
< MOVE 7 7
< INFO time_ms=1441 sims=256 value=0.610300 legal=8 stopped=sims
< SAMPLE 8 7
< TOP 7 7 visits=96 value=0.610300
< TOP 8 7 visits=41 value=0.587100
< TOP 6 7 visits=27 value=0.576400
< END
```

---

## 12. 协议演进

- 加 `INFO` / `TOP` 的 key、加新的中间行类型：不升版本，客户端必须忽略不认识的内容
- 在请求末尾追加可选 `key=value` 选项、在 READY 追加可选 `opt` 能力位：不升版本；客户端必须先检查能力位再发送选项
- 改字段顺序、改字段语义、增加必选行：必须升 `protocol` 到 `2`
- solver 在握手时报告自己的 `protocol`；client 只与支持的版本通信
- 同一 `protocol` 下，所有引擎（v0 / v2 / 第三方）的帧格式必须同构；`opt` 能力位可以不同

---

## 13. 与旧 solver.exe 协议的差异

旧格式（已废弃）：

```text
请求：<iterations> <player> <debug> + 225 个格子值
响应：可选 DEBUG 块 + 一行 "row col"
```

新协议的主要变化：

1. 增加 `READY` 握手
2. 请求增加 `max_ms`、`topk`
3. 响应改为 `MOVE` / `INFO` / `TOP` / `END` 帧
4. 不再有 `debug` 开关；提示所需信息由 `topk` 控制
5. 旧 `solver.exe` 已按本规范重写为 `src/v0/solver.cpp`

---

## 附录 A：NN 模型张量 ABI（v2 部署模型约定，不属于协议）

v2 的 C++ solver 通过 ONNX Runtime 加载模型，模型需满足：

| 项 | 约定 |
|---|---|
| 输入名 | `planes` |
| 输入形状 | `[B, 2, 15, 15]`，float32，B 动态 |
| 输入平面 | ch0 = 走子方棋子，ch1 = 对方棋子 |
| 输出名 | `policy`、`value` |
| `policy` | `[B, 225]` float32，概率，和为 1 |
| `value` | `[B, 1]` float32，走子方视角期望得分 `[0, 1]` |

实现约定：

- 合法着法由 solver 内部定义，先验在该集合上重新归一化
- 模型与本协议解耦：换模型只需保证上面的张量约定，求解器代码不用改
