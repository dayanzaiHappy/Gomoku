// src/v0/solver.cpp — 启发式 MCTS 求解器（协议 v1）
//
// 版本：v0（heuristic）
// 协议：PROTOCOL.md
// 构建：build.bat（g++ -O3）
//
// 搜索算法沿用原 tools/mcts_src/mcts_solver.cpp：
//   UCT + 启发式偏置 + 随机 rollout。
// 本文件只重写 I/O 层：READY 握手、search 请求、MOVE/INFO/TOP/END 帧。

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <iostream>
#include <limits>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "board.h"

using namespace gomoku;

std::mt19937 rng((unsigned int)time(0));

const double UCT_C = 1.414;
const double UCT_BIAS_B = 1e-2;
const double EPS = 0.2;
static const long long DEFAULT_SIMS = 100000;

// ===== 启发式评分 =====

int calculate(Board& board, int pos, int player) {
    int r = pos >> 4, c = pos & 15;
    int opponent = (player == BLACK) ? WHITE : BLACK;
    int live_four = 0, rush_four = 0, live_three = 0;
    int opp_live_four = 0, opp_rush_four = 0, opp_live_three = 0;
    int opp_five = 0;

    board[pos] = player;
    for (int d = 0; d < 4; d++) {
        int dr = DIRS[d][0], dc = DIRS[d][1];
        int cnt = 1, open = 0;
        int nr = r + dr, nc = c + dc;
        while (nr >= 0 && nr < SIZE && nc >= 0 && nc < SIZE && board[(nr << 4) | nc] == player) {
            cnt++; nr += dr; nc += dc;
        }
        if (nr >= 0 && nr < SIZE && nc >= 0 && nc < SIZE && board[(nr << 4) | nc] == EMPTY) open++;
        nr = r - dr; nc = c - dc;
        while (nr >= 0 && nr < SIZE && nc >= 0 && nc < SIZE && board[(nr << 4) | nc] == player) {
            cnt++; nr -= dr; nc -= dc;
        }
        if (nr >= 0 && nr < SIZE && nc >= 0 && nc < SIZE && board[(nr << 4) | nc] == EMPTY) open++;
        if (cnt >= 5) { board[pos] = EMPTY; return 1000000; }
        if (cnt == 4 && open == 2) live_four++;
        else if (cnt == 4 && open >= 1) rush_four++;
        else if (cnt == 3 && open == 2) live_three++;
    }

    board[pos] = opponent;
    for (int d = 0; d < 4; d++) {
        int dr = DIRS[d][0], dc = DIRS[d][1];
        int cnt = 1, open = 0;
        int nr = r + dr, nc = c + dc;
        while (nr >= 0 && nr < SIZE && nc >= 0 && nc < SIZE && board[(nr << 4) | nc] == opponent) {
            cnt++; nr += dr; nc += dc;
        }
        if (nr >= 0 && nr < SIZE && nc >= 0 && nc < SIZE && board[(nr << 4) | nc] == EMPTY) open++;
        nr = r - dr; nc = c - dc;
        while (nr >= 0 && nr < SIZE && nc >= 0 && nc < SIZE && board[(nr << 4) | nc] == opponent) {
            cnt++; nr -= dr; nc -= dc;
        }
        if (nr >= 0 && nr < SIZE && nc >= 0 && nc < SIZE && board[(nr << 4) | nc] == EMPTY) open++;
        if (cnt >= 5) opp_five++;
        if (cnt == 4 && open == 2) opp_live_four++;
        else if (cnt == 4 && open >= 1) opp_rush_four++;
        else if (cnt == 3 && open == 2) opp_live_three++;
    }
    board[pos] = EMPTY;

    int score = 0;
    score += 100000 * opp_five;
    score += 1000 * opp_live_four;
    score += 100 * opp_rush_four;
    score += 10 * opp_live_three;
    score += 10000 * live_four;
    score += 1100 * rush_four;
    score += 110 * live_three;
    return score;
}

// ===== 下棋策略：epsilon-greedy + 启发式 =====

int pick_move(int moves[], int &num_moves, Board& board, int player) {
    if (std::uniform_real_distribution<double>(0, 1)(rng) < EPS) {
        int idx = std::uniform_int_distribution<int>(0, num_moves - 1)(rng);
        int pos = moves[idx];
        moves[idx] = moves[--num_moves];
        return pos;
    }
    int h[225];
    for (int i = 0; i < num_moves; i++) h[i] = calculate(board, moves[i], player);
    int best = 0;
    for (int i = 1; i < num_moves; i++) {
        if (h[i] > h[best]) best = i;
    }
    int pos = moves[best];
    moves[best] = moves[--num_moves];
    return pos;
}

int simulation(Board& board, int player) {
    int moves[225];
    bool used[240];
    memset(used, 0, sizeof(used));
    int num_moves = board.get_moves(moves);
    for (int i = 0; i < num_moves; i++) used[moves[i]] = true;
    int sim_player = player;
    while (num_moves > 0) {
        int pos = pick_move(moves, num_moves, board, sim_player);
        used[pos] = false;
        board[pos] = sim_player;
        if (board.check_win_at(pos)) return sim_player;
        int r = pos >> 4, c = pos & 15;
        for (int dr = -1; dr <= 1; dr++) {
            for (int dc = -1; dc <= 1; dc++) {
                if (dr == 0 && dc == 0) continue;
                int nr = r + dr, nc = c + dc;
                if (nr < 0 || nr >= SIZE || nc < 0 || nc >= SIZE) continue;
                int npos = (nr << 4) | nc;
                if (board[npos] == EMPTY && !used[npos]) {
                    moves[num_moves++] = npos;
                    used[npos] = true;
                }
            }
        }
        sim_player = (sim_player == BLACK) ? WHITE : BLACK;
    }
    return 0;
}

// ===== MCTS =====

struct Node {
    Board board;
    int player;        // 该节点轮到谁走
    int move_pos;      // 走到此节点的落子位置（根为 -1）
    float score;       // 以当前 player 为视角
    int heuristic;     // calculate 评估值，用于 UCT bias
    int visits;
    int winner;        // 该节点是否已分出胜负（0=未结束，否则为胜方）
    int untried[225];  // 尚未扩展的走法
    int num_untried;
    int children[225]; // 已扩展的子节点索引
    int num_children;
};

double calc_uct(double score, int visits, int parent_visits, double value) {
    if (visits == 0) return 1e9 + UCT_BIAS_B * value;
    return score / visits + UCT_C * sqrt(log((double)parent_visits) / visits)
         + UCT_BIAS_B * value / (1.0 + visits);
}

int select(std::vector<Node> &pool, int path[], int &plen) {
    int idx = 0;
    path[plen++] = idx;
    while (true) {
        Node &node = pool[idx];
        if (node.num_untried > 0 || node.num_children == 0) break;
        int best = 0;
        double best_val = calc_uct(pool[node.children[0]].score, pool[node.children[0]].visits,
                                   node.visits, pool[node.children[0]].heuristic);
        for (int i = 1; i < node.num_children; i++) {
            double val = calc_uct(pool[node.children[i]].score, pool[node.children[i]].visits,
                                  node.visits, pool[node.children[i]].heuristic);
            if (val > best_val) { best_val = val; best = i; }
        }
        idx = node.children[best];
        path[plen++] = idx;
    }
    return idx;
}

int expand(std::vector<Node> &pool, int leaf_idx, int path[], int &plen) {
    Node &leaf = pool[leaf_idx];
    if (leaf.num_untried == 0) return leaf_idx;
    int pos = leaf.untried[--leaf.num_untried];
    Node child;
    child.board = leaf.board;
    child.heuristic = calculate(child.board, pos, leaf.player);
    child.board[pos] = leaf.player;
    child.player = leaf.player == BLACK ? WHITE : BLACK;
    child.move_pos = pos;
    child.score = 0.0f;
    child.visits = 0;
    child.winner = child.board.check_win_at(pos);
    child.num_children = 0;
    if (child.winner == 0) {
        child.num_untried = child.board.get_moves(child.untried);
    } else {
        child.num_untried = 0;
    }
    pool.push_back(child);
    int child_idx = (int)pool.size() - 1;
    leaf.children[leaf.num_children++] = child_idx;
    path[plen++] = child_idx;
    return child_idx;
}

void backPropagation(std::vector<Node> &pool, int path[], int plen, int winner, int sim_player) {
    double result;
    if (winner == 0) result = 0.5;
    else if (winner == sim_player) result = 0.0;
    else result = 1.0;
    for (int i = plen - 1; i >= 0; i--) {
        Node &n = pool[path[i]];
        n.visits++;
        n.score += result;
        result = 1.0 - result;
    }
}

// 空盘返回中心，其余按 board.h 的 8 邻域规则
int root_legal_moves(const Board &board, int moves[225]) {
    bool empty = true;
    for (int r = 0; r < SIZE && empty; r++) {
        for (int c = 0; c < SIZE; c++) {
            if (board[(r << 4) | c] != EMPTY) { empty = false; break; }
        }
    }
    if (empty) {
        moves[0] = ((SIZE / 2) << 4) | (SIZE / 2);
        return 1;
    }
    return board.get_moves(moves);
}

struct SearchOptions {
    double alpha = 0.1;  // 仅协议兼容；v0 没有先验，根噪声不生效
    double eps = 0.0;
    double tau = 0.0;    // 采样温度；0 = 关闭
};

struct ChildStat {
    int row;
    int col;
    int visits;
    double value;
};

struct SearchResult {
    int row = -1;
    int col = -1;
    int legal = 0;
    int sims = 0;
    double value = 0.5;
    bool stopped_time = false;
    bool has_sample = false;
    int sample_row = -1;
    int sample_col = -1;
    std::vector<ChildStat> top;
};

SearchResult run_search(const Board &board, int player, long long iterations,
                        long long max_ms, int topk, const SearchOptions &opt) {
    SearchResult res;

    std::vector<Node> pool;
    size_t reserve_n = (size_t)std::min<long long>(iterations + 100, 1000000);
    pool.reserve(reserve_n);

    Node root;
    root.board = board;
    root.player = player;
    root.move_pos = -1;
    root.score = 0.0f;
    root.heuristic = 0;
    root.visits = 0;
    root.winner = 0;
    root.num_untried = root_legal_moves(board, root.untried);
    root.num_children = 0;
    pool.push_back(root);

    res.legal = root.num_untried;
    if (res.legal == 0) {
        res.value = -1.0;
        return res;
    }

    auto t0 = std::chrono::steady_clock::now();
    long long done = 0;
    for (long long iter = 0; iter < iterations; iter++) {
        int path[225];
        int plen = 0;

        int leaf = select(pool, path, plen);
        int sim_node = expand(pool, leaf, path, plen);

        int winner = pool[sim_node].winner;
        if (winner == 0) {
            Board sim = pool[sim_node].board;
            winner = simulation(sim, pool[sim_node].player);
        }

        backPropagation(pool, path, plen, winner, pool[sim_node].player);
        done = iter + 1;

        if (max_ms > 0) {
            auto now = std::chrono::steady_clock::now();
            long long elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(now - t0).count();
            if (elapsed >= max_ms) {
                res.stopped_time = (done < iterations);
                break;
            }
        }
    }

    res.sims = (int)done;

    Node &r = pool[0];
    if (r.visits > 0) {
        res.value = (double)r.score / r.visits;
    }

    if (r.num_children == 0) {
        return res;
    }

    // 最佳子节点：visits 降序 → 根视角 value 降序 → index 升序
    int best_idx = r.children[0];
    for (int i = 1; i < r.num_children; i++) {
        int ci = r.children[i];
        Node &c = pool[ci];
        Node &b = pool[best_idx];
        if (c.visits != b.visits) {
            if (c.visits > b.visits) best_idx = ci;
        } else {
            double cv = c.visits > 0 ? 1.0 - (double)c.score / c.visits : -1.0;
            double bv = b.visits > 0 ? 1.0 - (double)b.score / b.visits : -1.0;
            if (cv != bv) {
                if (cv > bv) best_idx = ci;
            } else if (c.move_pos < b.move_pos) {
                best_idx = ci;
            }
        }
    }
    res.row = pool[best_idx].move_pos >> 4;
    res.col = pool[best_idx].move_pos & 15;

    std::vector<ChildStat> candidates;
    candidates.reserve(r.num_children);
    for (int i = 0; i < r.num_children; i++) {
        Node &c = pool[r.children[i]];
        if (c.visits <= 0) continue;
        ChildStat s;
        s.row = c.move_pos >> 4;
        s.col = c.move_pos & 15;
        s.visits = c.visits;
        s.value = 1.0 - (double)c.score / c.visits;  // 翻转到根走子方视角
        candidates.push_back(s);
    }
    std::sort(candidates.begin(), candidates.end(), [](const ChildStat &a, const ChildStat &b) {
        if (a.visits != b.visits) return a.visits > b.visits;
        if (a.value != b.value) return a.value > b.value;
        return a.row * SIZE + a.col < b.row * SIZE + b.col;
    });

    if (topk > 0) {
        size_t n = std::min<size_t>(candidates.size(), (size_t)topk);
        res.top.assign(candidates.begin(), candidates.begin() + n);
    }

    if (opt.tau > 0.0 && !candidates.empty()) {
        size_t k = candidates.size();
        if (topk > 0) k = std::min<size_t>(k, (size_t)topk);
        double inv_tau = 1.0 / std::max(opt.tau, 1e-6);
        std::vector<double> logw(k);
        double max_log = -std::numeric_limits<double>::infinity();
        for (size_t i = 0; i < k; i++) {
            logw[i] = std::log((double)candidates[i].visits) * inv_tau;
            if (logw[i] > max_log) max_log = logw[i];
        }
        std::vector<double> weights(k);
        for (size_t i = 0; i < k; i++) {
            weights[i] = std::exp(logw[i] - max_log);
        }
        std::random_device rd;
        std::seed_seq seq{rd(), rd(),
            (unsigned)std::chrono::high_resolution_clock::now().time_since_epoch().count()};
        std::mt19937 srng(seq);
        std::discrete_distribution<size_t> dist(weights.begin(), weights.end());
        size_t pick = dist(srng);
        res.has_sample = true;
        res.sample_row = candidates[pick].row;
        res.sample_col = candidates[pick].col;
    }
    return res;
}

// ===== 协议 I/O =====

static void send_error(int code, const char *message) {
    printf("ERROR %d %s\nEND\n", code, message);
    fflush(stdout);
}

int main() {
    printf("READY heuristic v0 1 sims_default=%lld opt=tau\nEND\n", DEFAULT_SIMS);
    fflush(stdout);

    std::string line;
    while (std::getline(std::cin, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.size() > 8192) {
            send_error(100, "line_too_long");
            continue;
        }

        std::istringstream iss(line);
        std::string cmd;
        if (!(iss >> cmd)) {
            send_error(100, "empty_request");
            continue;
        }

        if (cmd == "quit") {
            printf("OK\nEND\n");
            fflush(stdout);
            return 0;
        }
        if (cmd == "ping") {
            printf("PONG\nEND\n");
            fflush(stdout);
            continue;
        }
        if (cmd != "search") {
            send_error(100, "unknown_command");
            continue;
        }

        int player = 0, topk = 0;
        long long sims = 0, max_ms = 0;
        if (!(iss >> player >> sims >> max_ms >> topk)) {
            send_error(100, "malformed_request");
            continue;
        }
        if (player != BLACK && player != WHITE) {
            send_error(102, "invalid_player");
            continue;
        }
        if (sims < 0 || sims > 10000000LL || max_ms < 0 || max_ms > 10000000LL ||
            topk < 0 || topk > 64) {
            send_error(103, "param_out_of_range");
            continue;
        }
        if (sims == 0) sims = DEFAULT_SIMS;

        Board board;
        board.reset();
        bool bad_board = false;
        for (int i = 0; i < SIZE * SIZE; i++) {
            int v = 0;
            if (!(iss >> v)) { bad_board = true; break; }
            if (v < EMPTY || v > WHITE) { bad_board = true; break; }
            board[((i / SIZE) << 4) | (i % SIZE)] = v;
        }
        SearchOptions opt;
        bool bad_option = false;
        std::string token;
        while (!bad_board && (iss >> token)) {
            size_t eq = token.find('=');
            if (eq == std::string::npos || eq == 0 || eq + 1 == token.size()) {
                send_error(100, "malformed_option");
                bad_option = true;
                break;
            }
            std::string key = token.substr(0, eq);
            std::string value = token.substr(eq + 1);
            double d = 0.0;
            try {
                size_t pos = 0;
                d = std::stod(value, &pos);
                if (pos != value.size() || !std::isfinite(d)) {
                    throw std::invalid_argument("bad");
                }
            } catch (const std::exception &) {
                send_error(103, "invalid_option_value");
                bad_option = true;
                break;
            }
            if (key == "alpha") {
                if (!(d > 0.0)) {
                    send_error(103, "alpha_out_of_range");
                    bad_option = true;
                    break;
                }
                opt.alpha = d;
            } else if (key == "eps") {
                if (d < 0.0 || d > 1.0) {
                    send_error(103, "eps_out_of_range");
                    bad_option = true;
                    break;
                }
                opt.eps = d;
            } else if (key == "tau") {
                if (d < 0.0) {
                    send_error(103, "tau_out_of_range");
                    bad_option = true;
                    break;
                }
                opt.tau = d;
            } else {
                send_error(104, "unknown_option");
                bad_option = true;
                break;
            }
        }
        if (bad_board) {
            send_error(101, "invalid_board");
            continue;
        }
        if (bad_option) continue;

        auto t_parse = std::chrono::steady_clock::now();
        SearchResult res = run_search(board, player, sims, max_ms, topk, opt);
        auto t_end = std::chrono::steady_clock::now();
        long long time_ms = std::chrono::duration_cast<std::chrono::milliseconds>(t_end - t_parse).count();

        if (res.legal == 0) {
            printf("MOVE -1 -1\n");
            printf("INFO time_ms=0 sims=0 value=-1.000000 legal=0 stopped=no_move\n");
            printf("END\n");
            fflush(stdout);
            continue;
        }

        printf("MOVE %d %d\n", res.row, res.col);
        printf("INFO time_ms=%lld sims=%d value=%.6f legal=%d stopped=%s\n",
               time_ms, res.sims, res.value, res.legal,
               res.stopped_time ? "time" : "sims");
        if (res.has_sample) {
            printf("SAMPLE %d %d\n", res.sample_row, res.sample_col);
        }
        for (size_t i = 0; i < res.top.size(); i++) {
            printf("TOP %d %d visits=%d value=%.6f\n",
                   res.top[i].row, res.top[i].col, res.top[i].visits, res.top[i].value);
        }
        printf("END\n");
        fflush(stdout);
    }
    return 0;
}
