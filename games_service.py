"""
games_service.py - LinkedIn daily games automation using headless Playwright Firefox.

Plays: Patches, Zip, Mini Sudoku, Tango
Uses exact DOM selectors confirmed from open-source LinkedIn game solver repos.
"""
import json
import datetime
from playwright.sync_api import sync_playwright, Page
import database
from games_solver import solve_patches, solve_zip, solve_sudoku, solve_tango

_STATE_FILE = "games_state.json"

GAME_URLS = {
    "patches":     "https://www.linkedin.com/games/patches/",
    "zip":         "https://www.linkedin.com/games/zip/",
    "mini-sudoku": "https://www.linkedin.com/games/mini-sudoku/",
    "tango":       "https://www.linkedin.com/games/tango/",
}

# ── Helper: click via mousedown+mouseup (LinkedIn React requires both) ──
def _react_click(page: Page, selector: str):
    el = page.query_selector(selector)
    if el:
        el.dispatch_event("mousedown")
        el.dispatch_event("mouseup")
        return True
    return False

def _react_click_el(page: Page, el):
    el.dispatch_event("mousedown")
    el.dispatch_event("mouseup")

# ── Helper: get grid dimensions from CSS vars ──
def _get_grid_size(page: Page, grid_selector: str) -> tuple[int, int]:
    return page.evaluate(f"""() => {{
        const g = document.querySelector('{grid_selector}');
        if (!g) return [0, 0];
        const s = getComputedStyle(g);
        return [
            parseInt(s.getPropertyValue('--rows')) || 0,
            parseInt(s.getPropertyValue('--cols')) || 0
        ];
    }}""")

# ── Helper: wait for game to load ──
def _wait_for_game(page: Page, timeout=15000):
    page.wait_for_selector('[data-cell-idx]', timeout=timeout)
    page.wait_for_timeout(1000)  # extra settle time

# ── PATCHES ──────────────────────────────────────────────────────────────
def play_patches(page: Page) -> bool:
    try:
        page.goto(GAME_URLS["patches"], timeout=30000)
        _wait_for_game(page)

        # Get grid size
        rows, cols = _get_grid_size(page, '.patches-grid, .grid-game-board, [class*="grid"]')
        if not rows or not cols:
            # Fallback: count cells
            cells = page.query_selector_all('[data-cell-idx]')
            total = len(cells)
            import math
            rows = cols = int(math.sqrt(total))

        print(f"[games/patches] grid={rows}x{cols}", flush=True)

        # Extract anchors from aria-labels
        anchors = page.evaluate("""() => {
            const cells = document.querySelectorAll('[data-cell-idx]');
            const anchors = [];
            cells.forEach(cell => {
                const label = cell.getAttribute('aria-label') || '';
                const idx = parseInt(cell.getAttribute('data-cell-idx'));
                // Look for number in aria-label or cell content
                const numMatch = label.match(/\b(\d+)\b/) || (cell.textContent.match(/\b(\d+)\b/));
                // Look for color
                const colorMatch = label.match(/color[:\s]+([^,]+)/i);
                if (numMatch) {
                    anchors.push({
                        idx: idx,
                        size: parseInt(numMatch[1]),
                        color: colorMatch ? colorMatch[1].trim() : `color_${idx}`,
                        label: label
                    });
                }
            });
            return anchors;
        }""")

        if not anchors:
            print("[games/patches] no anchors found", flush=True)
            return False

        # Convert idx to (row, col) — 0-indexed to match solve_patches()
        parsed_anchors = []
        for a in anchors:
            row = a['idx'] // cols
            col = a['idx'] % cols
            parsed_anchors.append({
                'row': row, 'col': col,
                'color': a['color'], 'size': a['size']
            })

        print(f"[games/patches] anchors={parsed_anchors}", flush=True)
        solution = solve_patches(parsed_anchors, rows)
        if not solution:
            print("[games/patches] solver returned no solution", flush=True)
            return False

        # Click cells to fill each rectangle
        # Group by color and click all cells for each color region
        color_groups = {}
        for (r, c), color in solution.items():
            color_groups.setdefault(color, []).append((r, c))

        for color, cells in color_groups.items():
            # Find anchor for this color
            anchor = next((a for a in parsed_anchors if a['color'] == color), None)
            if not anchor:
                continue
            anchor_idx = anchor['row'] * cols + anchor['col']

            # Click each non-anchor cell in this color group
            for (r, c) in cells:
                cell_idx = r * cols + c
                if cell_idx == anchor_idx:
                    continue
                el = page.query_selector(f'[data-cell-idx="{cell_idx}"]')
                if el:
                    _react_click_el(page, el)
                    page.wait_for_timeout(100)

        page.wait_for_timeout(2000)
        # Check for win
        content = page.content()
        return any(w in content.lower() for w in ['you won', 'congratulations', 'solved', 'complete', 'great job', 'well done', 'learner'])

    except Exception as e:
        print(f"[games/patches] error: {e}", flush=True)
        return False

# ── ZIP ───────────────────────────────────────────────────────────────────
def play_zip(page: Page) -> bool:
    try:
        page.goto(GAME_URLS["zip"], timeout=30000)
        _wait_for_game(page)

        # FIRST: check for pre-embedded solution in #rehydrate-data
        rehydrate = page.evaluate("""() => {
            const el = document.querySelector('#rehydrate-data');
            if (!el) return null;
            try { return JSON.parse(el.textContent); } catch(e) { return null; }
        }""")

        solution_order = None
        if rehydrate and 'solution' in rehydrate:
            solution_order = rehydrate['solution']
            print(f"[games/zip] found embedded solution: {len(solution_order)} cells", flush=True)

        # Get grid info
        grid_info = page.evaluate("""() => {
            // Try both grid selectors
            const grid = document.querySelector('[data-testid="interactive-grid"]')
                       || document.querySelector('.grid-game-board');
            if (!grid) return null;
            const s = getComputedStyle(grid);
            const rows = parseInt(s.getPropertyValue('--rows'));
            const cols = parseInt(s.getPropertyValue('--cols'));

            // Get waypoints (numbered cells)
            const waypoints = {};
            document.querySelectorAll('[data-cell-idx]').forEach(cell => {
                const idx = parseInt(cell.getAttribute('data-cell-idx'));
                const content = cell.querySelector('[data-cell-content="true"]')
                              || cell.querySelector('.trail-cell-content');
                if (content) {
                    const num = parseInt(content.textContent.trim());
                    if (!isNaN(num) && num > 0) {
                        waypoints[idx] = num;
                    }
                }
            });
            return { rows, cols, waypoints };
        }""")

        if not grid_info or not grid_info.get('rows'):
            print("[games/zip] couldn't read grid", flush=True)
            return False

        rows, cols = grid_info['rows'], grid_info['cols']
        waypoints_by_idx = grid_info.get('waypoints', {})
        print(f"[games/zip] grid={rows}x{cols}, waypoints={waypoints_by_idx}", flush=True)

        # Convert waypoints to (row,col) format for solver
        waypoints = {}
        for idx_str, num in waypoints_by_idx.items():
            idx = int(idx_str)
            r, c = idx // cols + 1, idx % cols + 1
            waypoints[(r, c)] = num

        # Get click path
        if solution_order:
            # Embedded solution: solution_order is list of cell indices in path order
            path_indices = solution_order
        else:
            # Solve it
            path = solve_zip(rows, waypoints)
            if not path:
                print("[games/zip] solver failed", flush=True)
                return False
            path_indices = [(r - 1) * cols + (c - 1) for (r, c) in path]

        # Execute the path via mouse drag
        # Get bounding boxes of first and last cells to compute positions
        first_idx = path_indices[0]
        cell_rects = page.evaluate(f"""() => {{
            const rects = {{}};
            document.querySelectorAll('[data-cell-idx]').forEach(cell => {{
                const idx = cell.getAttribute('data-cell-idx');
                const r = cell.getBoundingClientRect();
                rects[idx] = {{ x: r.left + r.width/2, y: r.top + r.height/2 }};
            }});
            return rects;
        }}""")

        if not cell_rects:
            print("[games/zip] couldn't get cell positions", flush=True)
            return False

        # Draw path via mouse drag
        first_pos = cell_rects.get(str(first_idx))
        if not first_pos:
            print("[games/zip] first cell not found", flush=True)
            return False

        page.mouse.move(first_pos['x'], first_pos['y'])
        page.mouse.down()
        page.wait_for_timeout(200)

        for idx in path_indices[1:]:
            pos = cell_rects.get(str(idx))
            if pos:
                page.mouse.move(pos['x'], pos['y'])
                page.wait_for_timeout(50)

        page.mouse.up()
        page.wait_for_timeout(2000)

        content = page.content()
        return any(w in content.lower() for w in ['you won', 'congratulations', 'solved', 'complete', 'crushing', 'learner'])

    except Exception as e:
        print(f"[games/zip] error: {e}", flush=True)
        return False

# ── MINI SUDOKU ──────────────────────────────────────────────────────────
def play_sudoku(page: Page) -> bool:
    try:
        page.goto(GAME_URLS["mini-sudoku"], timeout=30000)
        _wait_for_game(page)

        # Extract grid: 6x6 with 2x3 boxes
        grid_data = page.evaluate("""() => {
            const cells = document.querySelectorAll('[data-cell-idx]');
            const total = cells.length;
            const size = Math.round(Math.sqrt(total));  // 6
            const grid = Array.from({length: size}, () => Array(size).fill(0));
            const locked = Array.from({length: size}, () => Array(size).fill(false));

            cells.forEach(cell => {
                const idx = parseInt(cell.getAttribute('data-cell-idx'));
                const row = Math.floor(idx / size);
                const col = idx % size;
                const isLocked = cell.classList.contains('sudoku-cell-prefilled');
                const contentEl = cell.querySelector('.sudoku-cell-content');
                const val = contentEl ? parseInt(contentEl.textContent.trim()) || 0 : 0;
                if (row < size && col < size) {
                    grid[row][col] = val;
                    locked[row][col] = isLocked;
                }
            });
            return { grid, locked, size };
        }""")

        if not grid_data:
            print("[games/sudoku] couldn't read grid", flush=True)
            return False

        grid = grid_data['grid']
        size = grid_data['size']
        print(f"[games/sudoku] grid={size}x{size}, given={sum(1 for r in grid for v in r if v>0)}", flush=True)

        # Solve (6x6 uses 2x3 boxes)
        box_w, box_h = (2, 3) if size == 6 else (2, 2) if size == 4 else (3, 3)
        solved = solve_sudoku([row[:] for row in grid], box_w, box_h)
        if not solved:
            print("[games/sudoku] solver failed", flush=True)
            return False

        # Fill in empty cells: click cell, then click number button
        for r in range(size):
            for c in range(size):
                if grid[r][c] == 0:
                    cell_idx = r * size + c
                    # Click the cell
                    cell_el = page.query_selector(f'[data-cell-idx="{cell_idx}"]')
                    if cell_el:
                        _react_click_el(page, cell_el)
                        page.wait_for_timeout(200)
                        # Click the number button
                        num = solved[r][c]
                        num_btn = page.query_selector(f'button[data-number="{num}"]')
                        if num_btn:
                            _react_click_el(page, num_btn)
                            page.wait_for_timeout(150)

        page.wait_for_timeout(2000)
        # Handle any popup
        close_btn = page.query_selector('button[aria-label*="close" i]')
        if close_btn:
            _react_click_el(page, close_btn)

        content = page.content()
        return any(w in content.lower() for w in ['you won', 'congratulations', 'solved', 'complete', 'learner', 'well done'])

    except Exception as e:
        print(f"[games/sudoku] error: {e}", flush=True)
        return False

# ── TANGO ────────────────────────────────────────────────────────────────
def play_tango(page: Page) -> bool:
    try:
        page.goto(GAME_URLS["tango"], timeout=30000)
        # Tango uses .lotka-grid
        page.wait_for_selector('.lotka-grid, [data-cell-idx]', timeout=15000)
        page.wait_for_timeout(1000)

        # Extract grid state and clues
        tango_data = page.evaluate("""() => {
            const cells = document.querySelectorAll('[data-cell-idx]');
            const size = 6;  // always 6x6
            const current = Array.from({length: size}, () => Array(size).fill('empty'));
            const locked = Array.from({length: size}, () => Array(size).fill(false));

            cells.forEach(cell => {
                const idx = parseInt(cell.getAttribute('data-cell-idx'));
                const row = Math.floor(idx / size);
                const col = idx % size;
                if (row >= size || col >= size) return;

                const isLocked = cell.classList.contains('lotka-cell--locked');
                locked[row][col] = isLocked;

                // Check SVG title for symbol
                const svgTitle = cell.querySelector('svg title');
                if (svgTitle) {
                    const t = svgTitle.textContent.toLowerCase();
                    if (t.includes('sun')) current[row][col] = 'sun';
                    else if (t.includes('moon')) current[row][col] = 'moon';
                }
                // Check img src
                const img = cell.querySelector('img');
                if (img) {
                    const src = img.src || '';
                    if (src.includes('sun')) current[row][col] = 'sun';
                    else if (src.includes('moon')) current[row][col] = 'moon';
                }
            });

            // Extract edge clues
            const clues = [];
            document.querySelectorAll('.lotka-cell-edge--right, .lotka-cell-edge--down').forEach(edge => {
                const svg = edge.querySelector('svg');
                const label = svg ? (svg.getAttribute('aria-label') || svg.getAttribute('aria-description') || '') : '';
                const type = label.includes('equal') || label.includes('=') ? 'same'
                           : label.includes('cross') || label.includes('x') || label.includes('differ') ? 'diff'
                           : null;
                if (!type) return;

                const cell = edge.closest('[data-cell-idx]');
                if (!cell) return;
                const idx = parseInt(cell.getAttribute('data-cell-idx'));
                const row = Math.floor(idx / size);
                const col = idx % size;

                if (edge.classList.contains('lotka-cell-edge--right') && col + 1 < size) {
                    clues.push({r1: row, c1: col, r2: row, c2: col+1, type});
                } else if (edge.classList.contains('lotka-cell-edge--down') && row + 1 < size) {
                    clues.push({r1: row, c1: col, r2: row+1, c2: col, type});
                }
            });

            return { current, locked, clues, size };
        }""")

        if not tango_data:
            print("[games/tango] couldn't read board", flush=True)
            return False

        current = tango_data['current']
        locked = tango_data['locked']
        clues = tango_data['clues']
        size = tango_data['size']
        print(f"[games/tango] grid={size}x{size}, clues={len(clues)}", flush=True)

        # Build initial grid for solver (use current locked values)
        initial = [[''] * size for _ in range(size)]
        for r in range(size):
            for c in range(size):
                if locked[r][c] and current[r][c] != 'empty':
                    initial[r][c] = current[r][c]

        solved = solve_tango(size, clues, initial)
        if not solved:
            print("[games/tango] solver failed", flush=True)
            return False

        # Determine how many clicks needed per cell (cycle: empty→sun→moon)
        for r in range(size):
            for c in range(size):
                if locked[r][c]:
                    continue
                target = solved[r][c]
                cell_idx = r * size + c
                cell_el = page.query_selector(f'[data-cell-idx="{cell_idx}"]')
                if not cell_el:
                    continue

                current_state = current[r][c]
                # Calculate clicks needed
                cycle = ['empty', 'sun', 'moon']
                cur_pos = cycle.index(current_state) if current_state in cycle else 0
                tgt_pos = cycle.index(target) if target in cycle else 0
                clicks = (tgt_pos - cur_pos) % 3

                for _ in range(clicks):
                    _react_click_el(page, cell_el)
                    page.wait_for_timeout(100)

        page.wait_for_timeout(2000)
        content = page.content()
        return any(w in content.lower() for w in ['you won', 'congratulations', 'solved', 'complete', 'learner'])

    except Exception as e:
        print(f"[games/tango] error: {e}", flush=True)
        return False

# ── MAIN RUNNER ──────────────────────────────────────────────────────────
def run_all_games() -> dict:
    """
    Run all 4 games with headless Firefox. Skip games already won today.
    Returns {game_id: {"won": bool, "skipped": bool, "elapsed": float}}
    """
    import time
    today = datetime.date.today().isoformat()
    state = database.load_state(_STATE_FILE, default={})

    results = {}
    games_to_play = []

    for game_id in ['patches', 'zip', 'mini-sudoku', 'tango']:
        if state.get(game_id, {}).get('won_date') == today:
            print(f"[games] {game_id} already won today, skipping", flush=True)
            results[game_id] = {"won": True, "skipped": True, "elapsed": 0.0}
        else:
            games_to_play.append(game_id)

    if not games_to_play:
        return results

    # Load LinkedIn cookies
    cookies = database.load_state("linkedin_cookies.json", default=None)

    with sync_playwright() as p:
        browser = p.firefox.launch(
            headless=True,
            firefox_user_prefs={
                "general.useragent.override": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0"
            }
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
            viewport={"width": 1280, "height": 720},
            locale="en-US",
        )

        # Load saved cookies
        if cookies and isinstance(cookies, list):
            try:
                context.add_cookies(cookies)
            except Exception as e:
                print(f"[games] cookie load error: {e}", flush=True)

        page = context.new_page()

        # Verify LinkedIn login
        page.goto("https://www.linkedin.com/feed/", timeout=30000)
        page.wait_for_timeout(2000)
        if 'login' in page.url or 'authwall' in page.url:
            print("[games] not logged in — aborting", flush=True)
            browser.close()
            return {"error": "not_logged_in"}

        game_funcs = {
            'patches': play_patches,
            'zip': play_zip,
            'mini-sudoku': play_sudoku,
            'tango': play_tango,
        }

        for game_id in games_to_play:
            print(f"[games] playing {game_id}...", flush=True)
            t0 = time.time()
            won = game_funcs[game_id](page)
            elapsed = time.time() - t0
            results[game_id] = {"won": won, "skipped": False, "elapsed": elapsed}
            print(f"[games] {game_id}: {'WON' if won else 'failed'} ({elapsed:.0f}s)", flush=True)
            if won:
                state[game_id] = {"won_date": today}
                database.save_state(_STATE_FILE, state)
            page.wait_for_timeout(1500)

        browser.close()

    return results
