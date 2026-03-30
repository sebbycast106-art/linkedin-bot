"""
games_solver.py — Pure Python solvers for all 4 LinkedIn daily games.

No browser / Playwright dependencies. Each solver takes structured data
and returns a solution that games_service.py can execute.
"""
from __future__ import annotations
import copy
from typing import Optional


# ---------------------------------------------------------------------------
# PATCHES solver
# ---------------------------------------------------------------------------

def solve_patches(anchors: list[dict], grid_size: int = 5) -> dict:
    """
    Solve the Patches puzzle: tile an NxN grid with non-overlapping axis-aligned
    rectangles. Each anchor specifies a cell that must be covered by its color's
    rectangle, plus the total area (size) of that rectangle.

    anchors: [{"row": 1, "col": 3, "color": "blue", "size": 5}, ...]
             row/col are 0-indexed.
    Returns: {(row, col): "color"} for every cell in the grid.
             Returns {} on failure.
    """
    N = grid_size
    colors = [a["color"] for a in anchors]
    # Build per-color info
    color_info = {}
    for a in anchors:
        color_info[a["color"]] = {"anchor_r": a["row"], "anchor_c": a["col"], "size": a["size"]}

    # Grid: None = unassigned
    grid: list[list[Optional[str]]] = [[None] * N for _ in range(N)]

    # Generate all valid rectangles for a color given its anchor and size
    def candidate_rects(color: str):
        info = color_info[color]
        r0, c0, sz = info["anchor_r"], info["anchor_c"], info["size"]
        rects = []
        # Enumerate all (r1,c1,r2,c2) rectangles that contain (r0,c0) and have area==sz
        for r1 in range(N):
            for c1 in range(N):
                for r2 in range(r1, N):
                    for c2 in range(c1, N):
                        h = r2 - r1 + 1
                        w = c2 - c1 + 1
                        if h * w == sz and r1 <= r0 <= r2 and c1 <= c0 <= c2:
                            rects.append((r1, c1, r2, c2))
        return rects

    def cells_of(r1, c1, r2, c2):
        return [(r, c) for r in range(r1, r2 + 1) for c in range(c1, c2 + 1)]

    def place(grid, color, r1, c1, r2, c2):
        g = [row[:] for row in grid]
        for r, c in cells_of(r1, c1, r2, c2):
            if g[r][c] is not None:
                return None  # collision
            g[r][c] = color
        return g

    def backtrack(grid, idx):
        if idx == len(colors):
            # Check all cells assigned
            if all(grid[r][c] is not None for r in range(N) for c in range(N)):
                return grid
            return None
        color = colors[idx]
        for rect in candidate_rects(color):
            r1, c1, r2, c2 = rect
            new_grid = place(grid, color, r1, c1, r2, c2)
            if new_grid is None:
                continue
            result = backtrack(new_grid, idx + 1)
            if result is not None:
                return result
        return None

    solution_grid = backtrack(grid, 0)
    if solution_grid is None:
        return {}

    result = {}
    for r in range(N):
        for c in range(N):
            result[(r, c)] = solution_grid[r][c]
    return result


# ---------------------------------------------------------------------------
# ZIP solver
# ---------------------------------------------------------------------------

def solve_zip(grid_size: int, waypoints: dict) -> list[tuple]:
    """
    Solve the Zip puzzle: find a Hamiltonian path through an NxN grid that
    visits numbered waypoints in numeric order.

    waypoints: {(row, col): number}  e.g. {(0,0): 1, (2,3): 2, (4,4): 3}
               Numbers are 1-based and must be visited in order.
    Returns: ordered list of (row, col) tuples covering every cell exactly once.
             Returns [] on failure.
    """
    N = grid_size
    total_cells = N * N

    # Sort waypoints by number
    sorted_wp = sorted(waypoints.items(), key=lambda x: x[1])
    # Required sequence of waypoint positions in order
    wp_seq = [pos for pos, _ in sorted_wp]

    visited = [[False] * N for _ in range(N)]
    path = []

    def neighbors(r, c):
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < N and 0 <= nc < N and not visited[nr][nc]:
                yield nr, nc

    def is_required_next(r, c, next_wp_idx):
        """If (r,c) is a waypoint and it's not the expected next one, reject."""
        if (r, c) in waypoints:
            wp_num = waypoints[(r, c)]
            # This waypoint's index in sorted order
            wp_idx = next(i for i, (p, _) in enumerate(sorted_wp) if p == (r, c))
            return wp_idx == next_wp_idx
        return True  # non-waypoint cell, fine

    def dfs(r, c, next_wp_idx):
        path.append((r, c))
        visited[r][c] = True

        if len(path) == total_cells:
            # Must have visited all waypoints
            if next_wp_idx == len(wp_seq):
                return True
            path.pop()
            visited[r][c] = False
            return False

        # Determine updated next_wp_idx
        nwi = next_wp_idx
        if (r, c) in waypoints:
            nwi = next_wp_idx + 1  # we just consumed this waypoint

        for nr, nc in neighbors(r, c):
            # If next cell is a waypoint, it must be the expected one
            if (nr, nc) in waypoints:
                wp_idx_of_next = next(i for i, (p, _) in enumerate(sorted_wp) if p == (nr, nc))
                if wp_idx_of_next != nwi:
                    continue  # skip — wrong waypoint
            if dfs(nr, nc, nwi):
                return True

        path.pop()
        visited[r][c] = False
        return False

    # Start from the first waypoint
    start_r, start_c = wp_seq[0]
    visited[start_r][start_c] = False  # ensure clean state
    if dfs(start_r, start_c, 0):
        return path

    # Fallback: try all possible starting cells if first waypoint start fails
    for r in range(N):
        for c in range(N):
            if (r, c) == (start_r, start_c):
                continue
            visited = [[False] * N for _ in range(N)]
            path = []
            if dfs(r, c, 0):
                return path

    return []


# ---------------------------------------------------------------------------
# SUDOKU solver
# ---------------------------------------------------------------------------

def solve_sudoku(grid: list[list[int]], box_w: int = 3, box_h: int = 3) -> list[list[int]]:
    """
    Solve a Sudoku puzzle of any size using constraint propagation + backtracking.

    grid: NxN list-of-lists with 0 for empty cells.
    box_w, box_h: box dimensions (width x height).
                  For 4x4: box_w=2, box_h=2.
                  For 6x6: box_w=3, box_h=2  (3 cols wide, 2 rows tall).
                  For 9x9: box_w=3, box_h=3.
    Returns: solved NxN grid, or original grid on failure.
    """
    N = len(grid)
    g = [row[:] for row in grid]  # deep copy

    def possible(r, c, num):
        # Row check
        if num in g[r]:
            return False
        # Col check
        if num in [g[i][c] for i in range(N)]:
            return False
        # Box check
        br = (r // box_h) * box_h
        bc = (c // box_w) * box_w
        for dr in range(box_h):
            for dc in range(box_w):
                if g[br + dr][bc + dc] == num:
                    return False
        return True

    def find_empty():
        # MRV heuristic: pick the empty cell with fewest candidates
        best = None
        best_count = N + 1
        for r in range(N):
            for c in range(N):
                if g[r][c] == 0:
                    count = sum(1 for n in range(1, N + 1) if possible(r, c, n))
                    if count < best_count:
                        best_count = count
                        best = (r, c)
                        if count == 0:
                            return best  # early exit — dead end
        return best

    def backtrack():
        cell = find_empty()
        if cell is None:
            return True  # solved
        r, c = cell
        for num in range(1, N + 1):
            if possible(r, c, num):
                g[r][c] = num
                if backtrack():
                    return True
                g[r][c] = 0
        return False

    if backtrack():
        return g
    return grid  # return original on failure


# ---------------------------------------------------------------------------
# TANGO solver
# ---------------------------------------------------------------------------

def solve_tango(grid_size: int, clues: list[dict], initial: list[list[str]] = None) -> list[list[str]]:
    """
    Solve the Tango puzzle (binary constraint puzzle with suns and moons).

    Rules:
      1. Each row and column has equal numbers of suns and moons (N/2 each).
      2. No 3 or more consecutive same symbol in any row or column.
      3. Clues: pairs of adjacent cells that must be "same" (=) or "different" (x).

    clues: [{"r1": 0, "c1": 0, "r2": 0, "c2": 1, "type": "same"}, ...]
           type is "same" or "diff"
    initial: pre-filled grid (empty string or 'sun'/'moon'). If not provided,
             starts from scratch.
    Returns: NxN grid of "sun"/"moon" strings.
             Returns [] on failure.
    """
    N = grid_size
    # 0 = unset, 1 = sun, 2 = moon
    grid = [[0] * N for _ in range(N)]

    # Seed grid from initial if provided
    if initial:
        for r in range(N):
            for c in range(N):
                val = initial[r][c] if r < len(initial) and c < len(initial[r]) else ''
                if val == 'sun':
                    grid[r][c] = 1
                elif val == 'moon':
                    grid[r][c] = 2

    def symbol_str(v):
        return "sun" if v == 1 else "moon"

    # Build clue lookup: (r1,c1,r2,c2) -> "same"/"diff"
    clue_map = {}
    for cl in clues:
        key = (cl["r1"], cl["c1"], cl["r2"], cl["c2"])
        clue_map[key] = cl["type"]
        # Also add reverse
        clue_map[(cl["r2"], cl["c2"], cl["r1"], cl["c1"])] = cl["type"]

    def is_valid_partial(r, c, val):
        """Check if placing val at (r,c) is valid so far."""
        grid[r][c] = val

        # Check clues involving (r,c)
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < N and 0 <= nc < N and grid[nr][nc] != 0:
                key = (r, c, nr, nc)
                if key in clue_map:
                    ct = clue_map[key]
                    if ct == "same" and grid[nr][nc] != val:
                        grid[r][c] = 0
                        return False
                    if ct == "diff" and grid[nr][nc] == val:
                        grid[r][c] = 0
                        return False

        # Check no 3 consecutive in row
        # Look left
        run = 1
        cc = c - 1
        while cc >= 0 and grid[r][cc] == val:
            run += 1
            cc -= 1
        cc = c + 1
        while cc < N and grid[r][cc] == val:
            run += 1
            cc += 1
        if run >= 3:
            grid[r][c] = 0
            return False

        # Check no 3 consecutive in col
        run = 1
        rr = r - 1
        while rr >= 0 and grid[rr][c] == val:
            run += 1
            rr -= 1
        rr = r + 1
        while rr < N and grid[rr][c] == val:
            run += 1
            rr += 1
        if run >= 3:
            grid[r][c] = 0
            return False

        # Check row balance: no more than N//2 of same symbol in this row
        row_suns = sum(1 for x in grid[r] if x == 1)
        row_moons = sum(1 for x in grid[r] if x == 2)
        if row_suns > N // 2 or row_moons > N // 2:
            grid[r][c] = 0
            return False

        # Check col balance
        col_suns = sum(1 for rr2 in range(N) if grid[rr2][c] == 1)
        col_moons = sum(1 for rr2 in range(N) if grid[rr2][c] == 2)
        if col_suns > N // 2 or col_moons > N // 2:
            grid[r][c] = 0
            return False

        grid[r][c] = 0
        return True

    def find_next_empty():
        for r in range(N):
            for c in range(N):
                if grid[r][c] == 0:
                    return r, c
        return None, None

    def backtrack():
        r, c = find_next_empty()
        if r is None:
            # Verify all clues satisfied
            for cl in clues:
                r1, c1, r2, c2, ct = cl["r1"], cl["c1"], cl["r2"], cl["c2"], cl["type"]
                v1, v2 = grid[r1][c1], grid[r2][c2]
                if ct == "same" and v1 != v2:
                    return False
                if ct == "diff" and v1 == v2:
                    return False
            return True

        for val in [1, 2]:  # 1=sun, 2=moon
            if is_valid_partial(r, c, val):
                grid[r][c] = val
                if backtrack():
                    return True
                grid[r][c] = 0
        return False

    if backtrack():
        return [[symbol_str(grid[r][c]) for c in range(N)] for r in range(N)]
    return []


# ---------------------------------------------------------------------------
# Self-test (run: python games_solver.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Testing Sudoku (4x4) ===")
    grid_4 = [
        [1, 0, 0, 0],
        [0, 0, 3, 0],
        [0, 2, 0, 0],
        [0, 0, 0, 4],
    ]
    sol = solve_sudoku(grid_4, box_w=2, box_h=2)
    for row in sol:
        print(row)

    print("\n=== Testing Sudoku (9x9) ===")
    grid_9 = [
        [5, 3, 0, 0, 7, 0, 0, 0, 0],
        [6, 0, 0, 1, 9, 5, 0, 0, 0],
        [0, 9, 8, 0, 0, 0, 0, 6, 0],
        [8, 0, 0, 0, 6, 0, 0, 0, 3],
        [4, 0, 0, 8, 0, 3, 0, 0, 1],
        [7, 0, 0, 0, 2, 0, 0, 0, 6],
        [0, 6, 0, 0, 0, 0, 2, 8, 0],
        [0, 0, 0, 4, 1, 9, 0, 0, 5],
        [0, 0, 0, 0, 8, 0, 0, 7, 9],
    ]
    sol9 = solve_sudoku(grid_9, box_w=3, box_h=3)
    for row in sol9:
        print(row)

    print("\n=== Testing Tango (4x4) ===")
    clues_t = [
        {"r1": 0, "c1": 0, "r2": 0, "c2": 1, "type": "same"},
        {"r1": 1, "c1": 1, "r2": 1, "c2": 2, "type": "diff"},
        {"r1": 2, "c1": 0, "r2": 3, "c2": 0, "type": "same"},
    ]
    sol_t = solve_tango(4, clues_t)
    if sol_t:
        for row in sol_t:
            print(row)
    else:
        print("No solution found")

    print("\n=== Testing Patches (5x5, 5 rectangles) ===")
    anchors_p = [
        {"row": 0, "col": 0, "color": "red",    "size": 6},
        {"row": 0, "col": 3, "color": "blue",   "size": 4},
        {"row": 2, "col": 2, "color": "green",  "size": 4},
        {"row": 3, "col": 0, "color": "yellow", "size": 6},
        {"row": 4, "col": 4, "color": "purple", "size": 5},
    ]
    sol_p = solve_patches(anchors_p, grid_size=5)
    if sol_p:
        for r in range(5):
            print([sol_p.get((r, c), "?") for c in range(5)])
    else:
        print("No solution found")

    print("\n=== Testing Zip (4x4) ===")
    wp = {(0, 0): 1, (0, 3): 2, (3, 3): 3, (3, 0): 4}
    path = solve_zip(4, wp)
    print(f"Path length: {len(path)} (expected 16)")
    print(f"First 5: {path[:5]}")
