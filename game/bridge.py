"""bridge.py — 求解器桥接层（协议 v1）

启动 `src/vN/solver.exe` 子进程，按 PROTOCOL.md 通信。
默认 v2；v2 缺失或启动失败时回退 v0。
"""

import os
import subprocess
import threading
from dataclasses import dataclass, field

from game.constants import AI_MAX_MS, AI_SIMS, SOLVER_VERSION, resource_path

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_BOARD_SIZE = 15


class SolverError(RuntimeError):
    """求解器启动失败、通信失败或返回 ERROR。"""


@dataclass
class SearchResult:
    row: int
    col: int
    value: float = 0.0
    legal: int = 0
    sims: int = 0
    time_ms: int = 0
    stopped: str = ""
    top: list = field(default_factory=list)  # [(row, col, visits, value)]
    sample: tuple = None  # (row, col)，tau>0 时由 solver 按 visits 采样


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _solver_path(version):
    """开发态走 src/vN；打包态走 solvers/vN。"""
    dev = os.path.join(_repo_root(), "src", version, "solver.exe")
    if os.path.isfile(dev):
        return dev
    packed = resource_path(os.path.join("solvers", version, "solver.exe"))
    if os.path.isfile(packed):
        return packed
    return None


class SolverClient:
    def __init__(self, version=None, startup_timeout=10.0):
        self.version = (version or SOLVER_VERSION).lower()
        self.startup_timeout = startup_timeout
        self.banner = ""
        self.sims_default = None
        self.features = set()
        self._proc = None
        self._start()

    # ---- 进程生命周期 ----

    def _start(self):
        candidates = [self.version]
        if self.version != "v0":
            candidates.append("v0")

        errors = []
        for version in candidates:
            path = _solver_path(version)
            if path is None:
                errors.append(f"{version}: solver.exe 不存在")
                continue

            proc = None
            try:
                proc = subprocess.Popen(
                    [path],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="ascii",
                    creationflags=_CREATE_NO_WINDOW,
                )
                lines = self._read_frame(proc, self.startup_timeout)
                if not lines or not lines[0].startswith("READY "):
                    raise SolverError(f"握手失败: {lines[:1]}")
                self._proc = proc
                self.version = version
                self.banner = lines[0]
                self.sims_default = None
                self.features = set()
                for token in lines[0].split()[4:]:
                    if token.startswith("sims_default="):
                        try:
                            self.sims_default = int(token.split("=", 1)[1])
                        except ValueError:
                            pass
                    elif token.startswith("opt="):
                        self.features = {f for f in token.split("=", 1)[1].split(",") if f}
                return
            except Exception as e:
                errors.append(f"{version}: {e}")
                if proc is not None:
                    try:
                        proc.kill()
                    except Exception:
                        pass

        raise SolverError("没有可用的 solver: " + "; ".join(errors))

    def supports(self, feature):
        """READY 中声明的可选能力，例如 noise / tau。"""
        return feature in self.features

    def close(self):
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.stdin.write("quit\n")
                proc.stdin.flush()
                proc.wait(timeout=0.5)
        except Exception:
            pass
        try:
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            try:
                if stream is not None:
                    stream.close()
            except Exception:
                pass

    def __del__(self):
        self.close()

    # ---- 通信 ----

    @staticmethod
    def _read_frame(proc, timeout):
        box = {}

        def reader():
            lines = []
            try:
                while True:
                    line = proc.stdout.readline()
                    if not line:
                        break
                    line = line.rstrip("\r\n")
                    lines.append(line)
                    if line == "END":
                        break
            except Exception as e:  # 管道被关闭等
                box["error"] = e
            box["lines"] = lines

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            try:
                proc.kill()
            except Exception:
                pass
            raise SolverError("solver 响应超时")
        if "error" in box:
            raise SolverError(str(box["error"]))
        return box.get("lines", [])

    def _exchange(self, command, timeout):
        """发一条请求并读回一个 frame；进程异常时重启并重试一次。"""
        last_error = None
        for _ in range(2):
            if self._proc is None or self._proc.poll() is not None:
                self._start()
            try:
                self._proc.stdin.write(command)
                self._proc.stdin.flush()
                return self._read_frame(self._proc, timeout)
            except Exception as e:
                last_error = e
                self.close()
        raise SolverError(f"通信失败: {last_error}")

    @staticmethod
    def _parse_frame(lines):
        result = None
        info = {}
        top = []
        sample = None

        for line in lines:
            parts = line.split()
            if not parts:
                continue
            tag = parts[0]
            if tag == "ERROR":
                raise SolverError(line)
            if tag == "MOVE" and len(parts) >= 3:
                result = SearchResult(row=int(parts[1]), col=int(parts[2]))
            elif tag == "SAMPLE" and len(parts) >= 3:
                sample = (int(parts[1]), int(parts[2]))
            elif tag == "INFO":
                for token in parts[1:]:
                    if "=" in token:
                        key, value = token.split("=", 1)
                        info[key] = value
            elif tag == "TOP" and len(parts) >= 3:
                kv = {}
                for token in parts[3:]:
                    if "=" in token:
                        key, value = token.split("=", 1)
                        kv[key] = value
                top.append((
                    int(parts[1]),
                    int(parts[2]),
                    int(kv.get("visits", "0")),
                    float(kv.get("value", "0")),
                ))

        if result is None:
            raise SolverError(f"响应缺少 MOVE: {lines[:2]}")

        result.value = float(info.get("value", "0"))
        result.legal = int(info.get("legal", "0"))
        result.sims = int(info.get("sims", "0"))
        result.time_ms = int(info.get("time_ms", "0"))
        result.stopped = info.get("stopped", "")
        result.top = top
        result.sample = sample
        if result.row < 0 or result.col < 0:
            return None
        return result

    # ---- 对外接口 ----

    def search(self, board, player, sims=None, max_ms=None, topk=0,
               alpha=None, eps=None, tau=None):
        """返回 SearchResult；无合法着法返回 None。

        alpha / eps：根节点 Dirichlet 噪声（需要 READY 声明 opt=noise）
        tau：按 visits^(1/tau) 采样并返回 SAMPLE 行（需要 opt=tau）

        board 可以是 game.board.Board，也可以是 15×15 的二维列表/数组。
        """
        if sims is None:
            sims = AI_SIMS
        if max_ms is None:
            max_ms = AI_MAX_MS
        if (alpha is not None or eps is not None) and not self.supports("noise"):
            raise SolverError("solver 不支持根噪声选项")
        if tau is not None and not self.supports("tau"):
            raise SolverError("solver 不支持 tau 采样选项")

        cells = board.board if hasattr(board, "board") else board
        flat = " ".join(str(cells[r][c]) for r in range(_BOARD_SIZE) for c in range(_BOARD_SIZE))
        command = f"search {int(player)} {int(sims)} {int(max_ms)} {int(topk)} {flat}"
        if alpha is not None:
            command += f" alpha={float(alpha):.9g}"
        if eps is not None:
            command += f" eps={float(eps):.9g}"
        if tau is not None:
            command += f" tau={float(tau):.9g}"
        command += "\n"
        timeout = (max_ms + 5000) / 1000.0 if max_ms else 60.0

        lines = self._exchange(command, timeout)
        return self._parse_frame(lines)

    def search_move(self, board, player, **kwargs):
        """只要落子坐标，兼容旧调用。"""
        result = self.search(board, player, **kwargs)
        return None if result is None else (result.row, result.col)
