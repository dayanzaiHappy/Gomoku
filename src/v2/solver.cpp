// src/v2/solver.cpp — 神经网络 MCTS 求解器（协议 v1）
//
// 版本：v2（nn）
// 协议：PROTOCOL.md
// 模型 ABI：planes[B,2,15,15] -> policy[B,225], value[B,1]
// 构建：build.bat（g++ + third_party/onnxruntime）
// 启动参数：--model <path> --threads <n> --radius <n>
//
// 搜索语义与训练侧 training/v1/solver.py 一致：
//   C_PUCT = 2.0；节点 score 以父节点视角累计；叶价值回传 1 - V。

#include <onnxruntime_cxx_api.h>

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <deque>
#include <iostream>
#include <limits>
#include <memory>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#define ENGINE_VERSION "v2"
static const int DEFAULT_RADIUS = 4;
static const long long DEFAULT_SIMS = 256;

static const int BOARD_SIZE = 15;
static const int N_CELLS = BOARD_SIZE * BOARD_SIZE;
static const int EMPTY = 0;
static const int BLACK = 1;
static const int WHITE = 2;
static const int DRAW = 3;
static const double C_PUCT = 2.0;

using Grid = std::array<int8_t, N_CELLS>;

static const int DIRS[4][2] = {{1, 0}, {0, 1}, {1, 1}, {1, -1}};

// ===== 棋盘 =====

static bool board_full(const Grid &g) {
    for (int i = 0; i < N_CELLS; i++) {
        if (g[i] == EMPTY) return false;
    }
    return true;
}

static int check_win(const Grid &g, int pos) {
    int player = g[pos];
    if (player == EMPTY) return 0;
    int r = pos / BOARD_SIZE, c = pos % BOARD_SIZE;
    for (int d = 0; d < 4; d++) {
        int dr = DIRS[d][0], dc = DIRS[d][1];
        int cnt = 1;
        for (int i = 1; i < 5; i++) {
            int nr = r + dr * i, nc = c + dc * i;
            if (nr < 0 || nr >= BOARD_SIZE || nc < 0 || nc >= BOARD_SIZE || g[nr * BOARD_SIZE + nc] != player) break;
            cnt++;
        }
        for (int i = 1; i < 5; i++) {
            int nr = r - dr * i, nc = c - dc * i;
            if (nr < 0 || nr >= BOARD_SIZE || nc < 0 || nc >= BOARD_SIZE || g[nr * BOARD_SIZE + nc] != player) break;
            cnt++;
        }
        if (cnt >= 5) return player;
    }
    return 0;
}

static std::vector<std::pair<int, int>> build_neigh(int radius) {
    std::vector<std::pair<int, int>> out;
    for (int dr = -radius; dr <= radius; dr++) {
        for (int dc = -radius; dc <= radius; dc++) {
            if (dr == 0 && dc == 0) continue;
            out.emplace_back(dr, dc);
        }
    }
    return out;
}

static void legal_moves(const Grid &g, const std::vector<std::pair<int, int>> &neigh,
                        std::vector<int> &out) {
    out.clear();
    bool empty = true;
    for (int i = 0; i < N_CELLS && empty; i++) {
        if (g[i] != EMPTY) empty = false;
    }
    if (empty) {
        out.push_back((BOARD_SIZE / 2) * BOARD_SIZE + (BOARD_SIZE / 2));
        return;
    }
    for (int r = 0; r < BOARD_SIZE; r++) {
        for (int c = 0; c < BOARD_SIZE; c++) {
            int pos = r * BOARD_SIZE + c;
            if (g[pos] != EMPTY) continue;
            bool is_near = false;
            for (const auto &d : neigh) {
                int nr = r + d.first, nc = c + d.second;
                if (nr < 0 || nr >= BOARD_SIZE || nc < 0 || nc >= BOARD_SIZE) continue;
                if (g[nr * BOARD_SIZE + nc] != EMPTY) { is_near = true; break; }
            }
            if (is_near) out.push_back(pos);
        }
    }
}

// ===== 网络推理 =====

struct Eval {
    std::vector<float> policy;
    float value = 0.5f;
};

class NNSolver {
public:
    NNSolver(const std::wstring &model_path, int threads, int radius)
        : env_(ORT_LOGGING_LEVEL_WARNING, "gomoku-solver"),
          radius_(radius),
          neigh_(build_neigh(radius)),
          mem_(Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault)) {
        Ort::SessionOptions opts;
        opts.SetIntraOpNumThreads(threads);
        opts.SetInterOpNumThreads(1);
        opts.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);
        opts.SetLogSeverityLevel(3);  // ERROR
        session_ = std::make_unique<Ort::Session>(env_, model_path.c_str(), opts);
    }

    int radius() const { return radius_; }

    Eval evaluate(const Grid &g, int player) {
        std::array<float, 2 * N_CELLS> planes{};
        for (int i = 0; i < N_CELLS; i++) {
            int v = g[i];
            planes[i] = (v == player) ? 1.0f : 0.0f;
            planes[N_CELLS + i] = (v == (3 - player)) ? 1.0f : 0.0f;
        }

        std::array<int64_t, 4> shape{1, 2, BOARD_SIZE, BOARD_SIZE};
        Ort::Value input = Ort::Value::CreateTensor<float>(
            mem_, planes.data(), planes.size(), shape.data(), shape.size());
        const char *in_names[] = {"planes"};
        const char *out_names[] = {"policy", "value"};
        std::vector<Ort::Value> outs =
            session_->Run(Ort::RunOptions{nullptr}, in_names, &input, 1, out_names, 2);

        if (outs.size() != 2) throw std::runtime_error("bad_output_count");
        if (outs[0].GetTensorTypeAndShapeInfo().GetElementCount() != (size_t)N_CELLS) {
            throw std::runtime_error("bad_policy_shape");
        }
        if (outs[1].GetTensorTypeAndShapeInfo().GetElementCount() != 1) {
            throw std::runtime_error("bad_value_shape");
        }

        const float *p = outs[0].GetTensorMutableData<float>();
        Eval ev;
        ev.policy.assign(p, p + N_CELLS);
        ev.value = outs[1].GetTensorMutableData<float>()[0];
        for (int i = 0; i < N_CELLS; i++) {
            if (!std::isfinite(ev.policy[i])) throw std::runtime_error("nan_policy");
        }
        if (!std::isfinite(ev.value)) throw std::runtime_error("nan_value");
        return ev;
    }

private:
    Ort::Env env_;
    std::unique_ptr<Ort::Session> session_;
    int radius_;
    std::vector<std::pair<int, int>> neigh_;
    Ort::MemoryInfo mem_;
};

// ===== MCTS =====

struct Node {
    Grid grid;
    int player = BLACK;   // 该节点轮到谁走
    int move = -1;        // 走到此节点的着法（根为 -1）
    int parent = -1;
    float prior = 0.0f;
    int visits = 0;
    double score = 0.0;   // 父节点视角
    int winner = 0;       // 0=未终局，1/2=胜方，DRAW=和棋
    bool expanded = false;
    std::vector<int> children;
};

struct SearchOptions {
    double alpha = 0.1;  // Dirichlet 浓度
    double eps = 0.0;    // 根先验噪声混合系数；0 = 关闭
    double tau = 0.0;    // 采样温度；0 = 关闭
};

struct ChildStat {
    int row;
    int col;
    int visits;
    double value;  // 根走子方视角
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

static double uct_value(const Node &child, int parent_visits) {
    if (child.visits == 0) {
        return 0.5 + C_PUCT * child.prior * std::sqrt((double)parent_visits + 1.0);
    }
    return child.score / child.visits
         + C_PUCT * child.prior * std::sqrt((double)parent_visits) / (1.0 + child.visits);
}

class MCTS {
public:
    MCTS(NNSolver &net) : net_(net), neigh_(build_neigh(net.radius())) {}

    SearchResult run(const Grid &grid, int player, long long sims, long long max_ms, int topk,
                     const SearchOptions &opt) {
        SearchResult res;
        nodes_.clear();

        Node root;
        root.grid = grid;
        root.player = player;
        root.move = -1;
        root.parent = -1;
        root.visits = 0;
        root.score = 0.0;
        root.winner = 0;
        root.expanded = false;
        root.children.clear();
        nodes_.push_back(root);

        std::vector<int> root_legal;
        legal_moves(grid, neigh_, root_legal);
        res.legal = (int)root_legal.size();
        if (res.legal == 0) {
            res.value = -1.0;
            return res;
        }

        auto t0 = std::chrono::steady_clock::now();

        // 根节点先评估并展开
        Eval root_eval = net_.evaluate(root.grid, root.player);
        expand_root(0, root_eval, root_legal);

        std::mt19937 rng;
        bool rng_ready = false;
        auto ensure_rng = [&]() -> std::mt19937 & {
            if (!rng_ready) {
                std::random_device rd;
                std::seed_seq seq{rd(), rd(),
                    (unsigned)std::chrono::high_resolution_clock::now().time_since_epoch().count()};
                rng.seed(seq);
                rng_ready = true;
            }
            return rng;
        };
        if (opt.eps > 0.0 && root_legal.size() > 1) {
            apply_root_noise(opt.alpha, opt.eps, ensure_rng());
        }

        long long done = 0;
        for (long long iter = 0; iter < sims; iter++) {
            int path[256];
            int plen = 0;
            int leaf = select(0, path, plen);

            Node &ln = nodes_[leaf];
            double result = 0.0;
            if (ln.winner != 0) {
                result = terminal_result(ln.winner, ln.player);
            } else {
                Eval ev = net_.evaluate(ln.grid, ln.player);
                expand(leaf, ev);
                result = (nodes_[leaf].winner == DRAW) ? 0.5 : 1.0 - (double)ev.value;
            }
            backprop(path, plen, result);
            done = iter + 1;

            if (max_ms > 0) {
                auto now = std::chrono::steady_clock::now();
                long long elapsed =
                    std::chrono::duration_cast<std::chrono::milliseconds>(now - t0).count();
                if (elapsed >= max_ms) {
                    res.stopped_time = (done < sims);
                    break;
                }
            }
        }

        res.sims = (int)done;
        Node &r = nodes_[0];
        if (r.visits > 0) {
            res.value = 1.0 - r.score / r.visits;  // 翻转到根走子方视角
        }

        if (r.children.empty()) return res;

        int best = r.children[0];
        for (size_t i = 1; i < r.children.size(); i++) {
            int ci = r.children[i];
            const Node &c = nodes_[ci];
            const Node &b = nodes_[best];
            if (c.visits != b.visits) {
                if (c.visits > b.visits) best = ci;
            } else {
                double cv = c.visits > 0 ? c.score / c.visits : -1.0;
                double bv = b.visits > 0 ? b.score / b.visits : -1.0;
                if (cv != bv) {
                    if (cv > bv) best = ci;
                } else if (c.move < b.move) {
                    best = ci;
                }
            }
        }
        res.row = nodes_[best].move / BOARD_SIZE;
        res.col = nodes_[best].move % BOARD_SIZE;

        std::vector<ChildStat> candidates;
        candidates.reserve(r.children.size());
        for (int ci : r.children) {
            const Node &c = nodes_[ci];
            if (c.visits <= 0) continue;
            ChildStat s;
            s.row = c.move / BOARD_SIZE;
            s.col = c.move % BOARD_SIZE;
            s.visits = c.visits;
            s.value = c.score / c.visits;  // 已是根走子方视角
            candidates.push_back(s);
        }
        std::sort(candidates.begin(), candidates.end(), [](const ChildStat &a, const ChildStat &b) {
            if (a.visits != b.visits) return a.visits > b.visits;
            if (a.value != b.value) return a.value > b.value;
            return a.row * BOARD_SIZE + a.col < b.row * BOARD_SIZE + b.col;
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
            std::discrete_distribution<size_t> dist(weights.begin(), weights.end());
            size_t pick = dist(ensure_rng());
            res.has_sample = true;
            res.sample_row = candidates[pick].row;
            res.sample_col = candidates[pick].col;
        }
        return res;
    }

private:
    void apply_root_noise(double alpha, double eps, std::mt19937 &rng) {
        Node &r = nodes_[0];
        if (r.children.size() < 2) return;
        std::gamma_distribution<double> gamma(alpha, 1.0);
        std::vector<double> noise(r.children.size());
        double sum = 0.0;
        for (size_t i = 0; i < r.children.size(); i++) {
            noise[i] = gamma(rng);
            sum += noise[i];
        }
        if (!std::isfinite(sum) || !(sum > 0.0)) return;
        for (size_t i = 0; i < r.children.size(); i++) {
            Node &c = nodes_[r.children[i]];
            double n = noise[i] / sum;
            c.prior = (float)((1.0 - eps) * (double)c.prior + eps * n);
        }
    }

    void expand_root(int idx, const Eval &ev, const std::vector<int> &legal) {
        Node &n = nodes_[idx];
        double sum = 0.0;
        for (int pos : legal) sum += ev.policy[pos];
        bool uniform = sum <= 1e-8;

        for (int pos : legal) {
            Node child;
            child.grid = n.grid;
            child.grid[pos] = (int8_t)n.player;
            child.player = 3 - n.player;
            child.move = pos;
            child.parent = idx;
            child.prior = uniform ? (float)(1.0 / legal.size()) : (float)(ev.policy[pos] / sum);
            child.visits = 0;
            child.score = 0.0;
            child.winner = check_win(child.grid, pos);
            if (child.winner == 0 && board_full(child.grid)) child.winner = DRAW;
            child.expanded = false;
            child.children.clear();
            nodes_.push_back(child);
            n.children.push_back((int)nodes_.size() - 1);
        }
        n.expanded = true;
    }

    void expand(int idx, const Eval &ev) {
        std::vector<int> legal;
        legal_moves(nodes_[idx].grid, neigh_, legal);
        if (legal.empty()) {
            nodes_[idx].winner = DRAW;
            nodes_[idx].expanded = true;
            return;
        }
        expand_root(idx, ev, legal);
    }

    int select(int root, int *path, int &plen) {
        int idx = root;
        path[plen++] = idx;
        while (true) {
            Node &n = nodes_[idx];
            if (!n.expanded || n.children.empty() || n.winner != 0) break;
            int best = n.children[0];
            double best_val = uct_value(nodes_[best], n.visits);
            for (size_t i = 1; i < n.children.size(); i++) {
                int ci = n.children[i];
                double val = uct_value(nodes_[ci], n.visits);
                if (val > best_val) {
                    best_val = val;
                    best = ci;
                }
            }
            idx = best;
            path[plen++] = idx;
        }
        return idx;
    }

    static double terminal_result(int winner, int leaf_player) {
        if (winner == DRAW) return 0.5;
        return (winner == leaf_player) ? 0.0 : 1.0;
    }

    void backprop(const int *path, int plen, double result) {
        for (int i = plen - 1; i >= 0; i--) {
            Node &n = nodes_[path[i]];
            n.visits++;
            n.score += result;
            result = 1.0 - result;
        }
    }

    NNSolver &net_;
    std::vector<std::pair<int, int>> neigh_;
    std::deque<Node> nodes_;
};

// ===== 命令行与协议 =====

static std::wstring exe_dir() {
    wchar_t buf[MAX_PATH];
    DWORD n = GetModuleFileNameW(nullptr, buf, MAX_PATH);
    std::wstring path(buf, n);
    size_t pos = path.find_last_of(L"\\/");
    return (pos == std::wstring::npos) ? L"." : path.substr(0, pos);
}

static void send_error(int code, const char *message) {
    printf("ERROR %d %s\nEND\n", code, message);
    fflush(stdout);
}

int wmain(int argc, wchar_t **argv) {
    std::wstring model_path = exe_dir() + L"\\model.onnx";
    int threads = 4;
    int radius = DEFAULT_RADIUS;

    for (int i = 1; i < argc; i++) {
        std::wstring a = argv[i];
        if (a == L"--model" && i + 1 < argc) {
            model_path = argv[++i];
        } else if (a == L"--threads" && i + 1 < argc) {
            threads = _wtoi(argv[++i]);
        } else if (a == L"--radius" && i + 1 < argc) {
            radius = _wtoi(argv[++i]);
        }
    }
    if (threads < 1) threads = 1;
    if (radius < 1) radius = 1;
    if (radius > 7) radius = 7;

    std::unique_ptr<NNSolver> net;
    try {
        net = std::make_unique<NNSolver>(model_path, threads, radius);
        // 启动自检：跑一次空盘前向，验证模型 ABI
        Grid empty{};
        net->evaluate(empty, BLACK);
    } catch (const std::exception &e) {
        fprintf(stderr, "model load failed: %s\n", e.what());
        send_error(202, "model_load_failed");
        return 2;
    }

    printf("READY nn %s 1 sims_default=%lld opt=noise,tau\nEND\n", ENGINE_VERSION, DEFAULT_SIMS);
    fflush(stdout);

    MCTS mcts(*net);
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

        Grid grid{};
        bool bad_board = false;
        for (int i = 0; i < N_CELLS; i++) {
            int v = 0;
            if (!(iss >> v)) { bad_board = true; break; }
            if (v < EMPTY || v > WHITE) { bad_board = true; break; }
            grid[i] = (int8_t)v;
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
        SearchResult res;
        try {
            res = mcts.run(grid, player, sims, max_ms, topk, opt);
        } catch (const std::exception &e) {
            fprintf(stderr, "inference failed: %s\n", e.what());
            send_error(201, "inference_failed");
            return 1;
        }
        auto t_end = std::chrono::steady_clock::now();
        long long time_ms =
            std::chrono::duration_cast<std::chrono::milliseconds>(t_end - t_parse).count();

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
