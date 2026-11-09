"""
constants.py — 五子棋游戏全局常量

棋盘规格
    SIZE            棋盘每边格数 (15×15)
    EMPTY/BLACK/WHITE  棋盘值：0=空, 1=黑, 2=白

像素尺寸
    CELL_SIZE       每个格子的像素宽度
    PADDING         棋盘边缘到窗口边缘的留白
    STONE_RADIUS    棋子的绘制半径
    INFO_HEIGHT     底部信息栏高度
    BOARD_PIXELS    棋盘区域总像素宽/高
    WINDOW_WIDTH    窗口宽度 (等于棋盘像素)
    WINDOW_HEIGHT   窗口高度 (棋盘像素 + 信息栏)

星位
    STAR_POINTS     棋盘上 5 个星位标记点 (row, col)

颜色 (R, G, B)
    COLOR_BOARD     棋盘底色 (木纹黄)
    COLOR_GRID      网格线 (深褐色)
    COLOR_BLACK     黑子
    COLOR_WHITE     白子
    COLOR_INFO_BG   底部信息栏背景
    COLOR_TEXT      通用文字
    COLOR_WINNER_BG 胜利弹窗半透明遮罩 (含 alpha)
    COLOR_BUTTON    按钮默认
    COLOR_BUTTON_HOVER  按钮悬停
    COLOR_BUTTON_ENABLED_TEXT   启用按钮文字
    COLOR_BUTTON_DISABLED_TEXT  禁用按钮文字
    COLOR_HIGLIGHT  最后落子高亮标记

其他
    FPS             游戏帧率
    RECORDS_DIR     棋谱文件保存目录
    DIRECTIONS      五子检测的四个方向向量 (row, col)
"""

SIZE = 15
EMPTY = 0
BLACK = 1
WHITE = 2

import os
import sys


def resource_path(name):
    """取资源/可执行文件的绝对路径：打包后走 _MEIPASS，开发时走 game/ 目录。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)

CELL_SIZE = 40
PADDING = 30
STONE_RADIUS = 17
INFO_HEIGHT = 50

BOARD_PIXELS = PADDING * 2 + (SIZE - 1) * CELL_SIZE
WINDOW_WIDTH = BOARD_PIXELS
WINDOW_HEIGHT = BOARD_PIXELS + INFO_HEIGHT

STAR_POINTS = [(3, 3), (3, 11), (7, 7), (11, 3), (11, 11)]

COLOR_BOARD = (220, 179, 92)
COLOR_GRID = (60, 40, 20)
COLOR_BLACK = (20, 20, 20)
COLOR_WHITE = (240, 240, 240)
COLOR_INFO_BG = (50, 50, 50)
COLOR_TEXT = (255, 255, 255)
COLOR_WINNER_BG = (0, 0, 0, 180)
COLOR_BUTTON = (100, 100, 100)
COLOR_BUTTON_HOVER = (140, 140, 140)
COLOR_BUTTON_ENABLED_TEXT = (255, 255, 255)
COLOR_BUTTON_DISABLED_TEXT = (120, 120, 120)
COLOR_HIGHLIGHT = (255, 50, 50)

FPS = 60

# 求解器：v2 默认，缺失时 bridge 自动回退 v0
SOLVER_VERSION = "v2"
AI_SIMS = 0              # 0 = 使用 solver 在 READY 里声明的 sims_default
AI_MAX_MS = 0            # 0 = 不设时间上限
DEBUG_ITERATIONS = 300000   # 调试工具显式使用的 v0 迭代数
HINT_SIMS = 256
HINT_TOPK = 5

# 人机对弈随机模式；评估模式不带这些参数
PLAY_TOPK = 3
PLAY_TAU = 0.6
PLAY_DIRICHLET_ALPHA = 0.1
PLAY_NOISE_EPS = 0.25

RECORDS_DIR = "records"

DIRECTIONS = [(1, 0), (0, 1), (1, 1), (1, -1)]
