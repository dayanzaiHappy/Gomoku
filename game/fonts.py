"""
fonts.py — 字体加载

load_font(size) -> pygame.font.Font
    尝试加载微软雅黑/SimHei 以支持中文，失败时回退到 Pygame 默认字体
"""

import os
import pygame


def load_font(size):
    windir = os.environ.get("WINDIR", r"C:\Windows")
    paths = [
        os.path.join(windir, "Fonts", "msyh.ttc"),
        os.path.join(windir, "Fonts", "simhei.ttf"),
    ]
    for path in paths:
        if os.path.exists(path):
            try:
                return pygame.font.Font(path, size)
            except Exception:
                continue
    return pygame.font.Font(None, size)
