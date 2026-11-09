"""
replay.py — 棋谱回放查看器

ReplayViewer 类

    __init__(lang)
        存储语言设置

    run() -> bool
        1. 弹 tkinter 文件对话框选择 .json 棋谱
        2. 取消选择 → 返回 True
        3. 切换窗口到回放界面
        4. 支持逐帧前进/后退、自动播放
        5. 返回主菜单 → True；窗口 X → False
"""

import os
import json
import pygame
from game.constants import SIZE, EMPTY, BLACK, WHITE, CELL_SIZE, PADDING
from game.constants import STONE_RADIUS, FPS
from game.constants import COLOR_BOARD, COLOR_GRID, COLOR_BLACK, COLOR_WHITE
from game.constants import COLOR_TEXT, COLOR_BUTTON, COLOR_BUTTON_HOVER
from game.constants import COLOR_INFO_BG, COLOR_HIGHLIGHT, BOARD_PIXELS
from game.constants import resource_path
from game.fonts import load_font
from game.lang import LANGUAGES

CONTROL_HEIGHT = 90
REPLAY_WIDTH = BOARD_PIXELS
REPLAY_HEIGHT = BOARD_PIXELS + CONTROL_HEIGHT


class ReplayViewer:
    def __init__(self, lang="zh"):
        self.lang = lang
        self.txt = LANGUAGES[lang]

    def _pick_file(self):
        try:
            import tkinter as tk
            from tkinter import filedialog
        except ImportError:
            return None
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        initial = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "records")
        if not os.path.isdir(initial):
            initial = os.path.dirname(__file__)
        path = filedialog.askopenfilename(
            title=self.txt["select_replay"],
            initialdir=initial,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        root.destroy()
        return path if path else None

    def _parse_file(self, path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        moves = data.get("moves", [])
        result = data.get("result", "?")
        date = data.get("date", "")
        return moves, result, date

    def _build_board(self, step):
        board = [[EMPTY] * SIZE for _ in range(SIZE)]
        for i in range(step):
            p, r, c = self.moves[i]["player"], self.moves[i]["row"], self.moves[i]["col"]
            board[r][c] = p
        return board

    def run(self):
        path = self._pick_file()
        if path is None:
            return True
        self.moves, self.result, self.date = self._parse_file(path)
        if not self.moves:
            return True

        self.total = len(self.moves)
        self.step = 0
        self.auto_playing = False
        self.last_auto_time = 0
        quit_requested = False

        screen = pygame.display.set_mode((REPLAY_WIDTH, REPLAY_HEIGHT))
        pygame.display.set_icon(pygame.image.load(resource_path("Gomoku.ico")))
        clock = pygame.time.Clock()
        font = load_font(24)
        font_small = load_font(20)
        pygame.display.set_caption(self.txt["replay"])

        btn_h = 32
        btn_gap = 10
        back_w = 90

        running = True
        while running:
            now = pygame.time.get_ticks()
            if self.auto_playing:
                if self.step < self.total and now - self.last_auto_time >= 1000:
                    self.step += 1
                    self.last_auto_time = now
                if self.step >= self.total:
                    self.auto_playing = False

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    quit_requested = True
                    running = False

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    if event.key == pygame.K_LEFT:
                        self.auto_playing = False
                        self.step = max(0, self.step - 1)
                    if event.key == pygame.K_RIGHT:
                        self.auto_playing = False
                        self.step = min(self.total, self.step + 1)

                if event.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = event.pos
                    if my < BOARD_PIXELS:
                        continue
                    ctrl_y = BOARD_PIXELS + 45
                    prev_w = font_small.render(self.txt["prev"], True, COLOR_TEXT).get_width() + 20
                    next_w = font_small.render(self.txt["next"], True, COLOR_TEXT).get_width() + 20
                    auto_label = self.txt["pause"] if self.auto_playing else self.txt["auto"]
                    auto_w = font_small.render(auto_label, True, COLOR_TEXT).get_width() + 20
                    bw_list = [prev_w, next_w, auto_w, back_w]
                    total_w = sum(bw_list) + btn_gap * 3
                    start_x = (REPLAY_WIDTH - total_w) // 2

                    rx = start_x
                    rects = []
                    for bw in bw_list:
                        rects.append(pygame.Rect(rx, ctrl_y, bw, btn_h))
                        rx += bw + btn_gap

                    if rects[0].collidepoint(mx, my):
                        self.auto_playing = False
                        self.step = max(0, self.step - 1)
                    elif rects[1].collidepoint(mx, my):
                        self.auto_playing = False
                        self.step = min(self.total, self.step + 1)
                    elif rects[2].collidepoint(mx, my):
                        if self.auto_playing:
                            self.auto_playing = False
                        else:
                            self.auto_playing = True
                            self.last_auto_time = now
                    elif rects[3].collidepoint(mx, my):
                        running = False

            screen.fill(COLOR_BOARD)
            for i in range(SIZE):
                x0, y0 = PADDING, PADDING + i * CELL_SIZE
                x1 = PADDING + (SIZE - 1) * CELL_SIZE
                pygame.draw.line(screen, COLOR_GRID, (x0, y0), (x1, y0), 1)
                pygame.draw.line(screen, COLOR_GRID, (y0, x0), (y0, x1), 1)

            for row, col in [(3, 3), (3, 11), (7, 7), (11, 3), (11, 11)]:
                cx = PADDING + col * CELL_SIZE
                cy = PADDING + row * CELL_SIZE
                pygame.draw.circle(screen, COLOR_GRID, (cx, cy), 4)

            board = self._build_board(self.step)
            for row in range(SIZE):
                for col in range(SIZE):
                    val = board[row][col]
                    if val == EMPTY:
                        continue
                    cx = PADDING + col * CELL_SIZE
                    cy = PADDING + row * CELL_SIZE
                    if val == BLACK:
                        pygame.draw.circle(screen, COLOR_BLACK, (cx, cy), STONE_RADIUS)
                        pygame.draw.circle(screen, (80, 80, 80), (cx - 3, cy - 3), 6)
                    else:
                        pygame.draw.circle(screen, COLOR_WHITE, (cx, cy), STONE_RADIUS)
                        pygame.draw.circle(screen, (200, 200, 200), (cx - 3, cy - 3), 6)
                    pygame.draw.circle(screen, COLOR_GRID, (cx, cy), STONE_RADIUS, 1)

            if self.step > 0:
                _, lr, lc = self.moves[self.step - 1]["player"], self.moves[self.step - 1]["row"], self.moves[self.step - 1]["col"]
                lx = PADDING + lc * CELL_SIZE
                ly = PADDING + lr * CELL_SIZE
                pygame.draw.circle(screen, COLOR_HIGHLIGHT, (lx, ly), 3)

            pygame.draw.rect(screen, COLOR_INFO_BG, (0, BOARD_PIXELS, REPLAY_WIDTH, CONTROL_HEIGHT))

            result_map = {"B": self.txt["black_wins"], "W": self.txt["white_wins"], "D": self.txt["draw"]}
            status_text = f"{self.step} / {self.total}    {result_map.get(self.result, '?')}"
            surf = font.render(status_text, True, COLOR_TEXT)
            sx = (REPLAY_WIDTH - surf.get_width()) // 2
            sy = BOARD_PIXELS + 8
            screen.blit(surf, (sx, sy))

            ctrl_y = BOARD_PIXELS + 45
            prev_w = font_small.render(self.txt["prev"], True, COLOR_TEXT).get_width() + 20
            next_w = font_small.render(self.txt["next"], True, COLOR_TEXT).get_width() + 20
            auto_label = self.txt["pause"] if self.auto_playing else self.txt["auto"]
            auto_w = font_small.render(auto_label, True, COLOR_TEXT).get_width() + 20
            bw_list = [prev_w, next_w, auto_w, back_w]
            total_w = sum(bw_list) + btn_gap * 3
            start_x = (REPLAY_WIDTH - total_w) // 2

            mouse_x, mouse_y = pygame.mouse.get_pos()
            rx = start_x
            for label, bw in [(self.txt["prev"], prev_w), (self.txt["next"], next_w),
                              (auto_label, auto_w), (self.txt["back_menu"], back_w)]:
                hover = rx <= mouse_x <= rx + bw and ctrl_y <= mouse_y <= ctrl_y + btn_h
                color = COLOR_BUTTON_HOVER if hover else COLOR_BUTTON
                pygame.draw.rect(screen, color, (rx, ctrl_y, bw, btn_h), border_radius=6)
                pygame.draw.rect(screen, COLOR_GRID, (rx, ctrl_y, bw, btn_h), 1, border_radius=6)
                surf = font_small.render(label, True, COLOR_TEXT)
                sx = rx + (bw - surf.get_width()) // 2
                sy = ctrl_y + (btn_h - surf.get_height()) // 2
                screen.blit(surf, (sx, sy))
                rx += bw + btn_gap

            pygame.display.flip()
            clock.tick(FPS)

        return not quit_requested
