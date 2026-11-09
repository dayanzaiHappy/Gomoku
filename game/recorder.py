"""
recorder.py — 对局记录与导出

GameRecorder 类

    __init__()
        记录对局开始时间，初始化空 moves 列表

    record_move(player, row, col)
        追加一步落子记录到 moves 列表

    pop_move()
        取出上一步记录（配合悔棋），返回 True/False

    save(result)
        对局结束后调用。根据 result 参数 ("B"/"W"/"D") 自动完成：
        1. 创建月份子目录：records/YYYYMM/
        2. 计算当日编号：扫描目录下已有文件，序号从 0000 递增
        3. 导出 JSON 文件到 records/YYYYMM/YYYYMMDD_XXXX.json
"""

import os
import json
from datetime import datetime
from game.constants import RECORDS_DIR


class GameRecorder:
    def __init__(self):
        self.start_time = datetime.now()
        self.moves = []

    def record_move(self, player, row, col):
        self.moves.append((player, row, col))

    def pop_move(self):
        if not self.moves:
            return False
        self.moves.pop()
        return True

    def save(self, result):
        dt = self.start_time
        date_str = dt.strftime("%Y%m%d")
        month_str = dt.strftime("%Y%m")

        record_dir = os.path.join(RECORDS_DIR, month_str)
        os.makedirs(record_dir, exist_ok=True)

        seq = 0
        for name in os.listdir(record_dir):
            if name.startswith(date_str) and name.endswith(".json"):
                try:
                    num = int(name[len(date_str) + 1:].replace(".json", ""))
                    seq = max(seq, num + 1)
                except ValueError:
                    continue
        seq_str = f"{seq:04d}"
        basename = f"{date_str}_{seq_str}"

        json_moves = []
        for player, row, col in self.moves:
            json_moves.append({"player": player, "row": row, "col": col})
        json_data = {
            "date": dt.strftime("%Y-%m-%d %H:%M:%S"),
            "result": result,
            "moves": json_moves
        }
        with open(os.path.join(record_dir, f"{basename}.json"), "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)

        return basename
