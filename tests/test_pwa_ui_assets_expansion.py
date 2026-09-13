"""
tests/test_pwa_ui_assets_expansion.py - Unit and Integration Tests for PWA, UI Aesthetics, and Build Assets.
Verifies TASK-081, TASK-082, TASK-083, TASK-089, TASK-090, TASK-114, TASK-115, TASK-118, TASK-120, TASK-121, TASK-124, TASK-129, TASK-134.
"""

from pathlib import Path
import pytest
from web.build_assets import build_minified_assets

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_ROOT / "web"


def test_style_css_frosted_glass_and_animations():
    """Verify web/style.css contains frosted glass properties, micro-animations, density classes, OLED theme, skeleton loader, and responsive bottom sheet."""
    style_path = WEB_DIR / "style.css"
    assert style_path.exists()
    content = style_path.read_text(encoding="utf-8")

    # 1. Custom CSS properties
    assert "--glass-bg" in content
    assert "--glass-border" in content
    assert "--neon-emerald" in content
    assert "--neon-indigo" in content
    assert "--oled-bg" in content

    # 2. Glassmorphism utility
    assert ".glassmorphism" in content or ".glass-card" in content

    # 3. 60fps Micro-animations
    assert "will-change:" in content
    assert "@keyframes ripple" in content
    assert "@keyframes pulseFlash" in content or ".pulse-flash" in content

    # 4. Layout Density Modifiers
    assert ".density-compact" in content
    assert ".density-comfort" in content
    assert ".density-ultra-dense" in content

    # 5. OLED Theme & High Contrast Focus Outline
    assert ".theme-oled" in content
    assert ":focus-visible" in content

    # 6. Skeleton Loader
    assert ".skeleton-loader" in content
    assert "@keyframes shimmer" in content

    # 7. Mobile Bottom Sheet CSS
    assert "@media (max-width: 768px)" in content
    assert ".bottom-sheet" in content

    # 8. Sparkline Canvas Styles
    assert ".sparkline-canvas" in content
    assert "width: 50px" in content
    assert "height: 20px" in content


def test_index_html_head_fonts_svg_and_aria():
    """Verify web/index.html imports Google Fonts Inter/Outfit, has SVG symbol library, quick-trade drawer, Cmd+K modal, mobile nav, offline banner, and ARIA attributes."""
    index_path = WEB_DIR / "index.html"
    assert index_path.exists()
    content = index_path.read_text(encoding="utf-8")

    # 1. Preconnect & Google Fonts Inter and Outfit
    assert 'rel="preconnect"' in content
    assert 'fonts.googleapis.com' in content
    assert 'family=Inter' in content
    assert 'family=Outfit' in content

    # 2. Inline SVG Symbol Library
    assert '<svg style="display:none"' in content
    assert '<symbol id="icon-bolt"' in content
    assert '<symbol id="icon-chart"' in content
    assert '<symbol id="icon-search"' in content

    # 3. Required HTML Structures
    assert 'id="quick-trade-drawer"' in content
    assert 'id="cmd-k-modal"' in content
    assert 'class="mobile-nav"' in content
    assert 'id="offline-banner"' in content

    # 4. WCAG 2.1 AA ARIA Attributes
    assert 'role="main"' in content
    assert 'role="navigation"' in content
    assert 'role="banner"' in content
    assert 'aria-label=' in content


def test_sw_js_service_worker_strategy():
    """Verify web/sw.js exists and implements cache-first static asset interceptor."""
    sw_path = WEB_DIR / "sw.js"
    assert sw_path.exists()
    content = sw_path.read_text(encoding="utf-8")

    assert "swing-trading" in content
    assert "caches.open" in content
    assert "caches.match" in content
    assert "self.addEventListener('fetch'" in content


def test_build_assets_minifier():
    """Verify web/build_assets.py generates minified files and returns valid compression stats."""
    stats = build_minified_assets()
    assert stats["style_css_orig_bytes"] > 0
    assert stats["style_css_min_bytes"] > 0
    assert stats["app_js_orig_bytes"] > 0
    assert stats["app_js_min_bytes"] > 0

    assert Path(stats["style_min_file"]).exists()
    assert Path(stats["app_min_file"]).exists()
    assert stats["css_savings_pct"] >= 0
    assert stats["js_savings_pct"] >= 0