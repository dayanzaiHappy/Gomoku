"""
board.py — 五子棋棋盘核心逻辑

Board 类

    __init__()
        初始化 15×15 空棋盘，当前玩家设为黑方，清空历史栈

    place(row, col) -> bool
        在 (row, col) 落子。若位置合法则写入棋盘、记录历史、切换玩家，返回 True；
        否则返回 False

    check_win(row, col) -> int | None
        从 (row, col) 沿四个方向统计连续同色棋子数。若 >=5 则返回落子方 (BLACK/WHITE)，
        否则返回 None

    undo() -> bool
        回退上一步：从历史栈弹出记录，恢复棋盘和当前玩家。无历史时返回 False

    is_valid(row, col) -> bool
        检查 (row, col) 是否在棋盘范围内且为空

    get_snapshot() -> list[list[int]]
        返回当前棋盘的深拷贝 (行切片复制)，供 recorder 独立保存

    is_full() -> bool
        棋盘是否已满 (无空位)
"""

from game.constants import SIZE, EMPTY, BLACK, WHITE, DIRECTIONS


class Board:
    def __init__(self):
        self.board = [[EMPTY] * SIZE for _ in range(SIZE)]
        self.current_player = BLACK
        self.history = []

    def place(self, row, col):
        if not self.is_valid(row, col):
            return False
        self.board[row][col] = self.current_player
        self.history.append((self.current_player, row, col))
        self.current_player = WHITE if self.current_player == BLACK else BLACK
        return True

    def check_win(self, row, col):
        player = self.board[row][col]
        if player == EMPTY:
            return None
        for dr, dc in DIRECTIONS:
            count = 1
            r, c = row + dr, col + dc
            while 0 <= r < SIZE and 0 <= c < SIZE and self.board[r][c] == player:
                count += 1
                r += dr
                c += dc
            r, c = row - dr, col - dc
            while 0 <= r < SIZE and 0 <= c < SIZE and self.board[r][c] == player:
                count += 1
                r -= dr
                c -= dc
            if count >= 5:
                return player
        return None

    def undo(self):
        if not self.history:
            return False
        player, row, col = self.history.pop()
        self.board[row][col] = EMPTY
        self.current_player = player
        return True

    def is_valid(self, row, col):
        return 0 <= row < SIZE and 0 <= col < SIZE and self.board[row][col] == EMPTY

    def get_snapshot(self):
        return [row[:] for row in self.board]

    def is_full(self):
        return all(cell != EMPTY for row in self.board for cell in row)
