"""
tests/test_hotkeys_palette.py - Unit tests for Workstation Hotkeys & Cmd+K Command Palette (Phase 4 Task C)
Verifies command palette HTML/CSS structure and JS keydown hotkey event listener bindings.
"""

from pathlib import Path
import pytest
from web.build_assets import build_minified_assets

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_ROOT / "web"


def test_cmd_k_modal_html_structure():
    """Verify web/index.html contains structure for #cmd-k-modal command palette."""
    index_path = WEB_DIR / "index.html"
    assert index_path.exists(), "web/index.html must exist"
    content = index_path.read_text(encoding="utf-8")

    # 1. Check modal container and accessibility attributes
    assert 'id="cmd-k-modal"' in content
    assert 'class="cmd-k-modal hidden"' in content
    assert 'role="dialog"' in content
    assert 'aria-modal="true"' in content
    assert 'aria-label="Command Palette"' in content

    # 2. Check input and results elements
    assert 'id="cmdKInput"' in content
    assert 'class="cmd-k-input"' in content
    assert 'id="cmdKResults"' in content
    assert 'class="cmd-k-results"' in content

    # 3. Check command items in palette
    assert 'data-action="tab-overview"' in content
    assert 'data-action="tab-screener"' in content
    assert 'data-action="tab-candidates"' in content
    assert 'data-action="quick-trade"' in content
    assert 'data-action="quick-buy"' in content
    assert 'data-action="quick-sell"' in content
    assert 'data-action="toggle-theme"' in content
    assert 'data-action="run-pipeline"' in content


def test_cmd_k_modal_and_selected_row_css_styles():
    """Verify web/style.css defines styles for command palette and table row navigation selection."""
    style_path = WEB_DIR / "style.css"
    assert style_path.exists(), "web/style.css must exist"
    content = style_path.read_text(encoding="utf-8")

    assert ".cmd-k-modal" in content
    assert ".cmd-k-container" in content
    assert ".cmd-k-input-wrapper" in content
    assert ".cmd-k-input" in content
    assert ".cmd-k-results" in content
    assert ".cmd-k-item" in content
    assert ".selected-row" in content


def test_hotkeys_and_command_palette_js_bindings():
    """Verify web/app.js contains JS functions and global keydown event listeners for hotkeys."""
    app_js_path = WEB_DIR / "app.js"
    assert app_js_path.exists(), "web/app.js must exist"
    content = app_js_path.read_text(encoding="utf-8")

    # 1. Required functions
    assert "function toggleCmdKModal()" in content
    assert "function executeCmdKAction" in content
    assert "function initCommandPalette()" in content
    assert "function navigateTableRows(" in content
    assert "function openQuickTrade(" in content

    # 2. Cmd+K / Ctrl+K hotkey binding
    assert "metaKey" in content and "ctrlKey" in content
    assert "toggleCmdKModal()" in content

    # 3. Quick Buy (B) and Quick Sell (S) hotkey bindings
    assert "e.key === 'b'" in content or "e.key === 'B'" in content
    assert "e.key === 's'" in content or "e.key === 'S'" in content
    assert "'BUY'" in content
    assert "'SELL'" in content

    # 4. Esc modal close hotkey binding
    assert "e.key === 'Escape'" in content
    assert "closeQuickTrade()" in content
    assert "closeExecutionModal()" in content

    # 5. Table row navigation hotkeys (ArrowUp / ArrowDown)
    assert "e.key === 'ArrowUp'" in content
    assert "e.key === 'ArrowDown'" in content
    assert "navigateTableRows(" in content


def test_minified_assets_build_sync():
    """Verify minification pipeline embeds hotkey and palette logic into production app.min.js and style.min.css."""
    res = build_minified_assets(WEB_DIR)
    assert res["files_processed"] == 2

    min_js_path = WEB_DIR / "app.min.js"
    assert min_js_path.exists()
    min_js_content = min_js_path.read_text(encoding="utf-8")
    assert "toggleCmdKModal" in min_js_content
    assert "navigateTableRows" in min_js_content
    assert "openQuickTrade" in min_js_content

    min_css_path = WEB_DIR / "style.min.css"
    assert min_css_path.exists()
    min_css_content = min_css_path.read_text(encoding="utf-8")
    assert ".cmd-k-modal" in min_css_content
    assert ".selected-row" in min_css_content
