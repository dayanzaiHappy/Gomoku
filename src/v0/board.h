// solver/src/board.h — 公共棋盘模块（header-only，零构建改动）
// 由 mcts_solver.cpp / NN_solver.cpp / selfplay.cpp / referee.cpp 共享。
// 逻辑与重构前逐字节一致：行为不变。

#ifndef GOMOKU_COMMON_H
#define GOMOKU_COMMON_H

namespace gomoku {

const int SIZE = 15;
const int EMPTY = 0;
const int BLACK = 1;
const int WHITE = 2;
const int DIRS[4][2] = {{1,0},{0,1},{1,1},{1,-1}};

// 棋盘，b[pos] 位打包 (pos = (r<<4)|c)，与旧 int board[240] 一致
class Board {
    int b[240];
public:
    void reset() {
        for (int i = 0; i < 240; i++) b[i] = 0;
    }
    int& operator[](int pos) { return b[pos]; }
    int operator[](int pos) const { return b[pos]; }

    int check_win_at(int pos) const {
        int r = pos >> 4, c = pos & 15;
        int player = b[pos];
        if (player == EMPTY) return 0;
        for (int d = 0; d < 4; d++) {
            int dr = DIRS[d][0], dc = DIRS[d][1];
            int count = 1;
            for (int i = 1; i < 5; i++) {
                int nr = r + dr * i, nc = c + dc * i;
                if (nr < 0 || nr >= SIZE || nc < 0 || nc >= SIZE || b[(nr << 4) | nc] != player) break;
                count++;
            }
            for (int i = 1; i < 5; i++) {
                int nr = r - dr * i, nc = c - dc * i;
                if (nr < 0 || nr >= SIZE || nc < 0 || nc >= SIZE || b[(nr << 4) | nc] != player) break;
                count++;
            }
            if (count >= 5) return player;
        }
        return 0;
    }

    int get_moves(int moves[225]) const {
        int n = 0;
        for (int r = 0; r < SIZE; r++) {
            for (int c = 0; c < SIZE; c++) {
                int pos = (r << 4) | c;
                if (b[pos] != EMPTY) continue;
                bool flag = false;
                for (int dr = -1; dr <= 1 && !flag; dr++) {
                    for (int dc = -1; dc <= 1 && !flag; dc++) {
                        if (dr == 0 && dc == 0) continue;
                        int nr = r + dr, nc = c + dc;
                        if (nr >= 0 && nr < SIZE && nc >= 0 && nc < SIZE && b[(nr << 4) | nc] != EMPTY)
                            flag = true;
                    }
                }
                if (flag) moves[n++] = pos;
            }
        }
        return n;
    }

    bool full() const {
        for (int r = 0; r < SIZE; r++)
            for (int c = 0; c < SIZE; c++)
                if (b[(r << 4) | c] == EMPTY) return false;
        return true;
    }
};

} // namespace gomoku

#endif // GOMOKU_COMMON_H
