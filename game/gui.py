"""
gui.py — 五子棋 Pygame 可视化界面

GameGUI 类

    __init__(lang)
        初始化 Pygame、创建窗口、加载字体、设置语言

    run_pvp()
        PvP 主循环。ESC 打开暂停菜单，可返回主菜单、退出程序或切换语言

    run_pvai()
        PvAI 主循环。人类执黑先手，Bot 执白

    _draw_board()
        绘制棋盘网格线和 5 个星位点

    _draw_stones(board)
        遍历棋盘所有棋子并绘制（黑子/白子，含高光效果）

    _draw_last_move(board)
        在最后落子位置画红色标记圈

    _draw_status(board, game_over, winner)
        底部信息栏显示当前轮到谁，或胜负结果

    _draw_popup(winner)
        半透明遮罩 + 胜者文字 + 两个按钮（再来一局 / 返回菜单）

    _handle_popup_click(pos) -> str | None
        检测弹窗按钮点击，返回 "restart" / "menu" / None

    _draw_pause_menu() -> list[dict]
        暂停菜单：遮罩 + 四个按钮（回到游戏 / 返回主菜单 / 退出游戏 / 语言切换）

    _screen_to_board(pos) -> tuple | None
        鼠标像素坐标 → 棋盘行列 (row, col)，超出范围返回 None

    _board_to_screen(row, col) -> tuple
        棋盘行列 → 屏幕像素坐标 (x, y)

run_menu()
    模块级函数：模式选择菜单。提供 PvP、PvAI、回放、语言切换、退出
"""

import sys
import pygame
from game.constants import *
from game.fonts import load_font
from game.lang import LANGUAGES
from game.board import Board
from game.recorder import GameRecorder
from game.replay import ReplayViewer
from game.bridge import SolverClient


class GameGUI:
    def __init__(self, lang="zh"):
        pygame.init()
        self.lang = lang
        self.txt = LANGUAGES[lang]
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_icon(pygame.image.load(resource_path("Gomoku.ico")))
        self.font = load_font(24)
        self.font_large = load_font(36)
        self.font_small = load_font(20)
        self.clock = pygame.time.Clock()
        pygame.display.set_caption(self.txt["title"])

    def _reload_lang(self):
        self.txt = LANGUAGES[self.lang]
        pygame.display.set_caption(self.txt["title"])

    def run_pvp(self):
        board = Board()
        recorder = GameRecorder()
        game_over = False
        winner = None
        paused = False
        popup_buttons = []
        pause_buttons = []
        running = True
        quit_requested = False

        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    quit_requested = True
                    running = False

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if game_over:
                            pass
                        else:
                            paused = not paused

                    if event.key == pygame.K_z and pygame.key.get_mods() & pygame.KMOD_CTRL:
                        if not paused and not game_over:
                            if board.undo():
                                recorder.pop_move()

                if paused:
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        for btn in pause_buttons:
                            if btn["rect"].collidepoint(event.pos):
                                key = btn["key"]
                                if key == "resume":
                                    paused = False
                                elif key == "back_menu":
                                    return True
                                elif key == "quit_game":
                                    pygame.quit()
                                    sys.exit(0)
                                elif key == "lang_toggle":
                                    self.lang = "en" if self.lang == "zh" else "zh"
                                    self._reload_lang()
                                break
                    continue

                if game_over:
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        action = self._handle_popup_click(event.pos, popup_buttons)
                        if action == "restart":
                            board = Board()
                            recorder = GameRecorder()
                            game_over = False
                            winner = None
                        elif action == "menu":
                            return True
                else:
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        pos = self._screen_to_board(event.pos)
                        if pos is not None:
                            row, col = pos
                            if board.is_valid(row, col):
                                player = board.current_player
                                recorder.record_move(player, row, col)
                                board.place(row, col)
                                win_result = board.check_win(row, col)
                                if win_result is not None:
                                    game_over = True
                                    winner = win_result
                                    result_str = "B" if win_result == BLACK else "W"
                                    recorder.save(result_str)
                                elif board.is_full():
                                    game_over = True
                                    winner = None
                                    recorder.save("D")

            self._draw(board, game_over, winner)
            if paused:
                pause_buttons = self._draw_pause_menu()
            if game_over and not paused:
                popup_buttons = self._draw_popup(winner)
            pygame.display.flip()
            self.clock.tick(FPS)

        pygame.quit()
        return not quit_requested

    def run_pvai(self):
        while True:
            human_is_black = self._choose_color()
            if human_is_black is None:
                return True

            human_color = BLACK if human_is_black else WHITE
            mcts = SolverClient()
            board = Board()
            recorder = GameRecorder()
            game_over = False
            winner = None
            paused = False
            popup_buttons = []
            pause_buttons = []
            running = True
            quit_requested = False
            restart = False
            hint = None

            if not human_is_black:
                board.place(7, 7)
                recorder.record_move(BLACK, 7, 7)

            while running:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        quit_requested = True
                        running = False
                        break

                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            if not game_over:
                                paused = not paused
                        if event.key == pygame.K_z and pygame.key.get_mods() & pygame.KMOD_CTRL:
                            if not paused and not game_over and len(board.history) >= 2:
                                if board.undo():
                                    recorder.pop_move()
                                    board.undo()
                                    recorder.pop_move()
                                    if mcts is not None:
                                        mcts.close()
                                    mcts = SolverClient()
                                    hint = None

                        if event.key == pygame.K_h and not paused and not game_over:
                            if board.current_player == human_color:
                                if hint is None:
                                    hint = self._request_hint(board, human_color, mcts)
                                else:
                                    hint = None

                    if paused:
                        if event.type == pygame.MOUSEBUTTONDOWN:
                            for btn in pause_buttons:
                                if btn["rect"].collidepoint(event.pos):
                                    key = btn["key"]
                                    if key == "resume":
                                        paused = False
                                    elif key == "back_menu":
                                        return True
                                    elif key == "quit_game":
                                        pygame.quit()
                                        sys.exit(0)
                                    elif key == "lang_toggle":
                                        self.lang = "en" if self.lang == "zh" else "zh"
                                        self._reload_lang()
                                    break
                        continue

                    if game_over:
                        if event.type == pygame.MOUSEBUTTONDOWN:
                            action = self._handle_popup_click(event.pos, popup_buttons)
                            if action == "restart":
                                restart = True
                                running = False
                                break
                            elif action == "menu":
                                return True
                    else:
                        if event.type == pygame.MOUSEBUTTONDOWN:
                            if (board.current_player == human_color
                                    and self._hint_button_rect().collidepoint(event.pos)):
                                if hint is None:
                                    hint = self._request_hint(board, human_color, mcts)
                                else:
                                    hint = None
                                continue
                            pos = self._screen_to_board(event.pos)
                            if pos is not None and board.current_player == human_color:
                                row, col = pos
                                if board.is_valid(row, col):
                                    player = board.current_player
                                    recorder.record_move(player, row, col)
                                    board.place(row, col)
                                    hint = None
                                    win_result = board.check_win(row, col)
                                    if win_result is not None:
                                        game_over = True
                                        winner = win_result
                                        result_str = "B" if win_result == BLACK else "W"
                                        recorder.save(result_str)
                                    elif board.is_full():
                                        game_over = True
                                        winner = None
                                        recorder.save("D")

                                    if not game_over:
                                        self._draw_bot_thinking(board)
                                        pygame.display.flip()
                                        bot_move = self._search_play(mcts, board, board.current_player)
                                        if bot_move is None:
                                            break
                                        if bot_move.sample is not None:
                                            bot_row, bot_col = bot_move.sample
                                        else:
                                            bot_row, bot_col = bot_move.row, bot_move.col
                                        recorder.record_move(board.current_player, bot_row, bot_col)
                                        board.place(bot_row, bot_col)
                                        win_result = board.check_win(bot_row, bot_col)
                                        if win_result is not None:
                                            game_over = True
                                            winner = win_result
                                            result_str = "B" if win_result == BLACK else "W"
                                            recorder.save(result_str)
                                        elif board.is_full():
                                            game_over = True
                                            winner = None
                                            recorder.save("D")

                show_hint = (not paused and not game_over
                             and board.current_player == human_color)
                self._draw(board, game_over, winner, hint=hint, hint_button=show_hint)
                if paused:
                    pause_buttons = self._draw_pause_menu()
                if game_over and not paused:
                    popup_buttons = self._draw_popup(winner)
                pygame.display.flip()
                self.clock.tick(FPS)

            if quit_requested:
                pygame.quit()
                return False
            if restart:
                continue

    def _draw_bot_thinking(self, board, text_key="bot_thinking"):
        self._draw_board()
        self._draw_stones(board)
        self._draw_last_move(board)
        info_rect = pygame.Rect(0, BOARD_PIXELS, WINDOW_WIDTH, INFO_HEIGHT)
        pygame.draw.rect(self.screen, COLOR_INFO_BG, info_rect)
        surface = self.font.render(self.txt[text_key], True, COLOR_TEXT)
        tx = (WINDOW_WIDTH - surface.get_width()) // 2
        ty = BOARD_PIXELS + (INFO_HEIGHT - surface.get_height()) // 2
        self.screen.blit(surface, (tx, ty))

    def _search_play(self, client, board, color):
        """人机对弈随机模式；solver 不支持的能力自动跳过。"""
        kwargs = {"topk": PLAY_TOPK}
        if client.supports("tau"):
            kwargs["tau"] = PLAY_TAU
        if client.supports("noise"):
            kwargs["alpha"] = PLAY_DIRICHLET_ALPHA
            kwargs["eps"] = PLAY_NOISE_EPS
        return client.search(board, color, **kwargs)

    def _request_hint(self, board, color, client):
        self._draw_bot_thinking(board, "hint_thinking")
        pygame.display.flip()
        try:
            return client.search(board, color, sims=HINT_SIMS, topk=HINT_TOPK)
        except Exception:
            return None

    def _draw(self, board, game_over, winner, hint=None, hint_button=False):
        self.screen.fill(COLOR_BOARD)
        self._draw_board()
        self._draw_stones(board)
        self._draw_last_move(board)
        self._draw_hint(board, hint)
        self._draw_status(board, game_over, winner, hint)
        if hint_button:
            self._draw_hint_button()

    def _draw_board(self):
        for i in range(SIZE):
            x0 = PADDING
            y0 = PADDING + i * CELL_SIZE
            x1 = PADDING + (SIZE - 1) * CELL_SIZE
            y1 = y0
            pygame.draw.line(self.screen, COLOR_GRID, (x0, y0), (x1, y1), 1)
            pygame.draw.line(self.screen, COLOR_GRID, (y0, x0), (y1, x1), 1)

        for row, col in STAR_POINTS:
            cx = PADDING + col * CELL_SIZE
            cy = PADDING + row * CELL_SIZE
            pygame.draw.circle(self.screen, COLOR_GRID, (cx, cy), 4)

    def _draw_stones(self, board):
        for row in range(SIZE):
            for col in range(SIZE):
                val = board.board[row][col]
                if val == EMPTY:
                    continue
                cx, cy = self._board_to_screen(row, col)
                if val == BLACK:
                    pygame.draw.circle(self.screen, COLOR_BLACK, (cx, cy), STONE_RADIUS)
                    pygame.draw.circle(self.screen, (80, 80, 80), (cx - 3, cy - 3), 6)
                else:
                    pygame.draw.circle(self.screen, COLOR_WHITE, (cx, cy), STONE_RADIUS)
                    pygame.draw.circle(self.screen, (200, 200, 200), (cx - 3, cy - 3), 6)
                pygame.draw.circle(self.screen, COLOR_GRID, (cx, cy), STONE_RADIUS, 1)

    def _draw_last_move(self, board):
        if not board.history:
            return
        _, row, col = board.history[-1]
        cx, cy = self._board_to_screen(row, col)
        pygame.draw.circle(self.screen, COLOR_HIGHLIGHT, (cx, cy), 3)

    def _draw_status(self, board, game_over, winner, hint=None):
        info_rect = pygame.Rect(0, BOARD_PIXELS, WINDOW_WIDTH, INFO_HEIGHT)
        pygame.draw.rect(self.screen, COLOR_INFO_BG, info_rect)

        if game_over and winner is None:
            text = self.txt["draw"]
        elif game_over:
            text = self.txt["black_wins"] if winner == BLACK else self.txt["white_wins"]
        else:
            text = self.txt["black_turn"] if board.current_player == BLACK else self.txt["white_turn"]
            if hint is not None:
                text += f"   |   {self.txt['win_rate']} {hint.value * 100:.0f}%"

        surface = self.font.render(text, True, COLOR_TEXT)
        tx = (WINDOW_WIDTH - surface.get_width()) // 2
        ty = BOARD_PIXELS + (INFO_HEIGHT - surface.get_height()) // 2
        self.screen.blit(surface, (tx, ty))

    def _hint_button_rect(self):
        return pygame.Rect(WINDOW_WIDTH - 104, BOARD_PIXELS + 7, 96, 36)

    @staticmethod
    def _value_color(value):
        v = max(0.0, min(1.0, value))
        if v < 0.5:
            return (255, int(255 * (v / 0.5)), 40)
        return (int(255 * (1.0 - (v - 0.5) / 0.5)), 220, 40)

    def _draw_hint(self, board, hint):
        if hint is None or not hint.top:
            return
        # top 已按 visits 降序；倒序绘制，让 1 号候选在最上层
        ranked = list(enumerate(hint.top, start=1))
        for rank, (row, col, _visits, value) in reversed(ranked):
            cx, cy = self._board_to_screen(row, col)
            color = self._value_color(value)
            surf = pygame.Surface((STONE_RADIUS * 2, STONE_RADIUS * 2), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*color, 150), (STONE_RADIUS, STONE_RADIUS), STONE_RADIUS - 2)
            pygame.draw.circle(surf, (*COLOR_GRID, 200), (STONE_RADIUS, STONE_RADIUS),
                               STONE_RADIUS - 2, 1)
            self.screen.blit(surf, (cx - STONE_RADIUS, cy - STONE_RADIUS))
            label = self.font_small.render(str(rank), True, (20, 20, 20))
            self.screen.blit(label, (cx - label.get_width() // 2,
                                     cy - label.get_height() // 2))
        cx, cy = self._board_to_screen(hint.row, hint.col)
        pygame.draw.circle(self.screen, (0, 120, 255), (cx, cy), STONE_RADIUS + 4, 4)

    def _draw_hint_button(self):
        rect = self._hint_button_rect()
        hover = rect.collidepoint(pygame.mouse.get_pos())
        color = COLOR_BUTTON_HOVER if hover else COLOR_BUTTON
        pygame.draw.rect(self.screen, color, rect, border_radius=6)
        pygame.draw.rect(self.screen, COLOR_GRID, rect, 1, border_radius=6)
        label = self.font_small.render(self.txt["hint"], True, COLOR_TEXT)
        self.screen.blit(label, (rect.centerx - label.get_width() // 2,
                                 rect.centery - label.get_height() // 2))

    def _draw_popup(self, winner):
        popup_w = 340
        popup_h = 180
        px = (WINDOW_WIDTH - popup_w) // 2
        py = (BOARD_PIXELS - popup_h) // 2

        overlay = pygame.Surface((WINDOW_WIDTH, BOARD_PIXELS), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        pygame.draw.rect(self.screen, (60, 60, 60), (px, py, popup_w, popup_h), border_radius=10)
        pygame.draw.rect(self.screen, COLOR_GRID, (px, py, popup_w, popup_h), 2, border_radius=10)

        if winner is None:
            title_text = self.txt["draw"]
        else:
            title_text = self.txt["black_wins"] if winner == BLACK else self.txt["white_wins"]
        title_surface = self.font_large.render(title_text, True, COLOR_TEXT)
        tx = px + (popup_w - title_surface.get_width()) // 2
        ty = py + 30
        self.screen.blit(title_surface, (tx, ty))

        btn_w = 120
        btn_h = 42
        btn_y = py + popup_h - btn_h - 30
        btn_x1 = px + 30
        btn_x2 = px + popup_w - 30 - btn_w
        mouse_x, mouse_y = pygame.mouse.get_pos()

        buttons = []
        for label, bx in [(self.txt["play_again"], btn_x1), (self.txt["back_menu"], btn_x2)]:
            hover = bx <= mouse_x <= bx + btn_w and btn_y <= mouse_y <= btn_y + btn_h
            color = COLOR_BUTTON_HOVER if hover else COLOR_BUTTON
            pygame.draw.rect(self.screen, color, (bx, btn_y, btn_w, btn_h), border_radius=6)
            pygame.draw.rect(self.screen, COLOR_GRID, (bx, btn_y, btn_w, btn_h), 1, border_radius=6)
            btn_surface = self.font_small.render(label, True, COLOR_BUTTON_ENABLED_TEXT)
            bx_center = bx + (btn_w - btn_surface.get_width()) // 2
            by_center = btn_y + (btn_h - btn_surface.get_height()) // 2
            self.screen.blit(btn_surface, (bx_center, by_center))
            buttons.append({"key": label, "rect": pygame.Rect(bx, btn_y, btn_w, btn_h)})

        return buttons

    def _handle_popup_click(self, pos, buttons):
        for btn in buttons:
            if btn["rect"].collidepoint(pos):
                return "restart" if btn["key"] == self.txt["play_again"] else "menu"
        return None

    def _draw_pause_menu(self):
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))

        panel_w = 280
        panel_h = 300
        px = (WINDOW_WIDTH - panel_w) // 2
        py = (WINDOW_HEIGHT - panel_h) // 2
        pygame.draw.rect(self.screen, (50, 50, 50), (px, py, panel_w, panel_h), border_radius=12)
        pygame.draw.rect(self.screen, COLOR_GRID, (px, py, panel_w, panel_h), 2, border_radius=12)

        title_surface = self.font.render(self.txt["pause"], True, COLOR_TEXT)
        tx = px + (panel_w - title_surface.get_width()) // 2
        ty = py + 20
        self.screen.blit(title_surface, (tx, ty))

        btn_w = 200
        btn_h = 40
        btn_gap = 10
        start_y = py + 65
        btn_x = px + (panel_w - btn_w) // 2
        mouse_x, mouse_y = pygame.mouse.get_pos()

        items = [
            ("resume", self.txt["resume"]),
            ("back_menu", self.txt["back_menu"]),
            ("lang_toggle", self.txt["lang_btn"]),
            ("quit_game", self.txt["quit_game"]),
        ]

        buttons = []
        for i, (key, label) in enumerate(items):
            by = start_y + i * (btn_h + btn_gap)
            hover = btn_x <= mouse_x <= btn_x + btn_w and by <= mouse_y <= by + btn_h
            color = COLOR_BUTTON_HOVER if hover else COLOR_BUTTON
            pygame.draw.rect(self.screen, color, (btn_x, by, btn_w, btn_h), border_radius=6)
            pygame.draw.rect(self.screen, COLOR_GRID, (btn_x, by, btn_w, btn_h), 1, border_radius=6)
            btn_surface = self.font_small.render(label, True, COLOR_TEXT)
            bx_c = btn_x + (btn_w - btn_surface.get_width()) // 2
            by_c = by + (btn_h - btn_surface.get_height()) // 2
            self.screen.blit(btn_surface, (bx_c, by_c))
            buttons.append({"key": key, "rect": pygame.Rect(btn_x, by, btn_w, btn_h)})

        return buttons

    def _choose_color(self):
        self.screen.fill(COLOR_BOARD)
        self._draw_board()
        info_rect = pygame.Rect(0, BOARD_PIXELS, WINDOW_WIDTH, INFO_HEIGHT)
        pygame.draw.rect(self.screen, COLOR_INFO_BG, info_rect)
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))

        panel_w = 300
        panel_h = 220
        px = (WINDOW_WIDTH - panel_w) // 2
        py = (WINDOW_HEIGHT - panel_h) // 2
        pygame.draw.rect(self.screen, (50, 50, 50), (px, py, panel_w, panel_h), border_radius=12)
        pygame.draw.rect(self.screen, COLOR_GRID, (px, py, panel_w, panel_h), 2, border_radius=12)

        title_surface = self.font.render(self.txt["choose_color"], True, COLOR_TEXT)
        tx = px + (panel_w - title_surface.get_width()) // 2
        ty = py + 25
        self.screen.blit(title_surface, (tx, ty))

        btn_w = 200
        btn_h = 44
        btn_x = px + (panel_w - btn_w) // 2
        mouse_x, mouse_y = pygame.mouse.get_pos()

        items = [
            (True, self.txt["play_black"]),
            (False, self.txt["play_white"]),
        ]

        buttons = []
        for i, (key, label) in enumerate(items):
            by = py + 75 + i * (btn_h + 15)
            hover = btn_x <= mouse_x <= btn_x + btn_w and by <= mouse_y <= by + btn_h
            color = COLOR_BUTTON_HOVER if hover else COLOR_BUTTON
            pygame.draw.rect(self.screen, color, (btn_x, by, btn_w, btn_h), border_radius=6)
            pygame.draw.rect(self.screen, COLOR_GRID, (btn_x, by, btn_w, btn_h), 1, border_radius=6)
            btn_surface = self.font_small.render(label, True, COLOR_TEXT)
            bx_c = btn_x + (btn_w - btn_surface.get_width()) // 2
            by_c = by + (btn_h - btn_surface.get_height()) // 2
            self.screen.blit(btn_surface, (bx_c, by_c))
            buttons.append({"key": key, "rect": pygame.Rect(btn_x, by, btn_w, btn_h)})

        pygame.display.flip()

        waiting = True
        while waiting:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return None
                if event.type == pygame.MOUSEBUTTONDOWN:
                    for btn in buttons:
                        if btn["rect"].collidepoint(event.pos):
                            return btn["key"]
            self.clock.tick(FPS)

    def _screen_to_board(self, pos):
        x, y = pos
        if y >= BOARD_PIXELS:
            return None
        col = round((x - PADDING) / CELL_SIZE)
        row = round((y - PADDING) / CELL_SIZE)
        if 0 <= row < SIZE and 0 <= col < SIZE:
            return row, col
        return None

    def _board_to_screen(self, row, col):
        x = PADDING + col * CELL_SIZE
        y = PADDING + row * CELL_SIZE
        return x, y


def run_menu():
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_icon(pygame.image.load(resource_path("Gomoku.ico")))
    clock = pygame.time.Clock()

    lang = "zh"
    txt = LANGUAGES[lang]

    font_large = load_font(52)
    font_normal = load_font(36)
    font_small = load_font(28)

    btn_w = 260
    btn_h = 60
    btn_x = (WINDOW_WIDTH - btn_w) // 2

    btn_y1 = 170
    btn_y2 = 240
    btn_y3 = 310

    lang_btn_w = 100
    lang_btn_h = 36
    lang_btn_x = 60
    lang_btn_y = 420

    quit_btn_w = 100
    quit_btn_h = 36
    quit_btn_x = WINDOW_WIDTH - 60 - quit_btn_w
    quit_btn_y = 420

    running = True
    while running:
        screen.fill(COLOR_BOARD)
        mouse_x, mouse_y = pygame.mouse.get_pos()

        title_surface = font_large.render(txt["title"], True, COLOR_GRID)
        tx = (WINDOW_WIDTH - title_surface.get_width()) // 2
        screen.blit(title_surface, (tx, 80))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                break

            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if btn_x <= mx <= btn_x + btn_w and btn_y1 <= my <= btn_y1 + btn_h:
                    gui = GameGUI(lang)
                    if not gui.run_pvp():
                        running = False
                        break
                    pygame.init()
                    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
                    pygame.display.set_icon(pygame.image.load(resource_path("Gomoku.ico")))
                    font_large = load_font(52)
                    font_normal = load_font(36)
                    font_small = load_font(28)
                    clock = pygame.time.Clock()
                if btn_x <= mx <= btn_x + btn_w and btn_y2 <= my <= btn_y2 + btn_h:
                    gui = GameGUI(lang)
                    if not gui.run_pvai():
                        running = False
                        break
                    pygame.init()
                    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
                    pygame.display.set_icon(pygame.image.load(resource_path("Gomoku.ico")))
                    font_large = load_font(52)
                    font_normal = load_font(36)
                    font_small = load_font(28)
                    clock = pygame.time.Clock()
                if btn_x <= mx <= btn_x + btn_w and btn_y3 <= my <= btn_y3 + btn_h:
                    viewer = ReplayViewer(lang)
                    if not viewer.run():
                        running = False
                        break
                    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
                    pygame.display.set_icon(pygame.image.load(resource_path("Gomoku.ico")))
                    pygame.display.set_caption(txt["title"] + " - " + txt["select_mode"])
                    font_large = load_font(52)
                    font_normal = load_font(36)
                    font_small = load_font(28)
                    clock = pygame.time.Clock()
                if lang_btn_x <= mx <= lang_btn_x + lang_btn_w and lang_btn_y <= my <= lang_btn_y + lang_btn_h:
                    lang = "en" if lang == "zh" else "zh"
                    txt = LANGUAGES[lang]
                    pygame.display.set_caption(txt["title"] + " - " + txt["select_mode"])
                if quit_btn_x <= mx <= quit_btn_x + quit_btn_w and quit_btn_y <= my <= quit_btn_y + quit_btn_h:
                    running = False

        if not running:
            continue

        for label, btn_y, enabled in [(txt["pvp"], btn_y1, True), (txt["pvai"], btn_y2, True), (txt["replay"], btn_y3, True)]:
            hover = btn_x <= mouse_x <= btn_x + btn_w and btn_y <= mouse_y <= btn_y + btn_h
            color = COLOR_BUTTON_HOVER if (hover and enabled) else COLOR_BUTTON
            pygame.draw.rect(screen, color, (btn_x, btn_y, btn_w, btn_h), border_radius=10)
            pygame.draw.rect(screen, COLOR_GRID, (btn_x, btn_y, btn_w, btn_h), 2, border_radius=10)
            text_color = COLOR_TEXT if enabled else COLOR_BUTTON_DISABLED_TEXT
            text_surface = font_normal.render(label, True, text_color)
            tx2 = btn_x + (btn_w - text_surface.get_width()) // 2
            ty2 = btn_y + (btn_h - text_surface.get_height()) // 2
            screen.blit(text_surface, (tx2, ty2))

        for label, bx, by in [(txt["lang_btn"], lang_btn_x, lang_btn_y), (txt["quit"], quit_btn_x, quit_btn_y)]:
            hover = bx <= mouse_x <= bx + lang_btn_w and by <= mouse_y <= by + lang_btn_h
            color = COLOR_BUTTON_HOVER if hover else COLOR_BUTTON
            pygame.draw.rect(screen, color, (bx, by, lang_btn_w, lang_btn_h), border_radius=6)
            pygame.draw.rect(screen, COLOR_GRID, (bx, by, lang_btn_w, lang_btn_h), 1, border_radius=6)
            label_surface = font_small.render(label, True, COLOR_TEXT)
            lx = bx + (lang_btn_w - label_surface.get_width()) // 2
            ly = by + (lang_btn_h - label_surface.get_height()) // 2
            screen.blit(label_surface, (lx, ly))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
