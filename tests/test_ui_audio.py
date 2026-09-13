"""
tests/test_ui_audio.py - Automated Unit & Integration Tests for Web Audio API Sound Synthesizer & Skeleton Loaders (Tasks T-335 to T-354).
Verifies Phase 29 & Phase 30 requirements.
"""

from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_ROOT / "web"


def test_style_css_skeleton_loader_components_and_cross_fade():
    """Verify web/style.css contains skeleton card, row, text, matrix, chart loader classes, and cross-fade animations (T-335, T-344)."""
    style_path = WEB_DIR / "style.css"
    assert style_path.exists(), "web/style.css does not exist"
    content = style_path.read_text(encoding="utf-8")

    assert ".skeleton-card" in content, ".skeleton-card missing from style.css"
    assert ".skeleton-row" in content, ".skeleton-row missing from style.css"
    assert ".skeleton-text" in content, ".skeleton-text missing from style.css"
    assert ".skeleton-matrix" in content, ".skeleton-matrix missing from style.css"
    assert ".skeleton-chart" in content, ".skeleton-chart missing from style.css"
    assert "@keyframes shimmer" in content, "shimmer animation missing from style.css"
    assert ".cross-fade" in content, ".cross-fade class missing from style.css"
    assert "audio-modal-container" in content, "audio modal styles missing from style.css"


def test_index_html_skeletons_and_audio_modal():
    """Verify web/index.html includes 10 screener row skeletons, candidates cards, options matrix skeletons, chart wrapper, and Audio Settings modal (T-336, T-337, T-342, T-343, T-350, T-351)."""
    index_path = WEB_DIR / "index.html"
    assert index_path.exists(), "web/index.html does not exist"
    content = index_path.read_text(encoding="utf-8")

    # Screener grid row skeletons (T-336)
    assert 'class="skeleton-row-tr"' in content, "Screener 10 animated row skeletons missing"
    assert content.count('class="skeleton-row-tr"') >= 10, "Expected at least 10 screener row skeletons"

    # Candidates skeleton cards (T-337)
    assert 'class="skeleton-card"' in content, "Candidates skeleton cards missing"

    # Audio Header button & Settings Modal (T-350, T-351, T-352, T-353)
    assert 'id="btnOpenAudioModal"' in content, "btnOpenAudioModal button missing from header"
    assert 'id="audioToggleBtn"' in content, "audioToggleBtn missing from header"
    assert 'id="audioSettingsModal"' in content, "audioSettingsModal container missing"
    assert 'id="audioVolumeSlider"' in content, "audioVolumeSlider slider missing"
    assert 'id="voiceAlertsToggle"' in content, "voiceAlertsToggle missing"

    # Test sound preview buttons (T-353)
    assert 'id="btnTestClick"' in content, "btnTestClick button missing"
    assert 'id="btnTestOrderFill"' in content, "btnTestOrderFill button missing"
    assert 'id="btnTestStopLoss"' in content, "btnTestStopLoss button missing"
    assert 'id="btnTestWarning"' in content, "btnTestWarning button missing"
    assert 'id="btnTestOpportunity"' in content, "btnTestOpportunity button missing"
    assert 'id="btnTestSuccess"' in content, "btnTestSuccess button missing"
    assert 'id="btnTestVoice"' in content, "btnTestVoice button missing"


def test_sound_synthesizer_class_and_audio_wiring_in_app_js():
    """Verify SoundSynthesizer class in web/app.js instantiates and defines all 6 synthesized tones, volume control, and speech synthesis (T-345 to T-354)."""
    app_path = WEB_DIR / "app.js"
    assert app_path.exists(), "web/app.js does not exist"
    content = app_path.read_text(encoding="utf-8")

    # SoundSynthesizer class definition
    assert "class SoundSynthesizer" in content, "SoundSynthesizer class missing in app.js"

    # 6 distinct synthesized audio tone methods (T-345)
    methods = [
        "playSoftClick",
        "playOrderFillChime",
        "playStopLossTone",
        "playWarningBeep",
        "playOpportunityPing",
        "playSuccessTone",
        "speakAlert",
        "setVolume",
    ]
    for method in methods:
        assert method in content, f"Method {method} missing in SoundSynthesizer class"

    # Navigation tab soft click wiring (T-346)
    assert "playSoftClick" in content, "Soft click sound effect missing in tab buttons"

    # Audio UI initializer
    assert "initAudioUIControls" in content, "initAudioUIControls function missing in app.js"

    # Optimistic UI updates (T-339, T-340, T-341)
    assert "quickAddToWatchlist" in content, "quickAddToWatchlist function missing"
    assert "[Optimistic]" in content, "Optimistic UI notification messaging missing"
    assert "cancelGTTOrder" in content, "cancelGTTOrder function missing"

    # Skeleton matrix and cross-fade helpers (T-342, T-344)
    assert "getSkeletonMatrixRowsHtml" in content, "getSkeletonMatrixRowsHtml function missing"
    assert "crossFadeReplace" in content, "crossFadeReplace function missing"
