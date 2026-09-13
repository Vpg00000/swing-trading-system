"""
web/build_assets.py - Automated CSS & JS Asset Minifier (TASK-115)
Minifies web production static assets (CSS, JS) to reduce bundle size and bandwidth overhead.
"""

import os
import re
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_ROOT / "web"


def minify_css(css_text: str) -> str:
    """Minifies CSS content by removing comments and superfluous whitespace."""
    if not css_text:
        return ""
    # Remove CSS comments
    css = re.sub(r'/\*[\s\S]*?\*/', '', css_text)
    # Collapse multiple whitespaces/newlines into single space
    css = re.sub(r'\s+', ' ', css)
    # Remove space around delimiters
    css = re.sub(r'\s*([\{\}:;,])\s*', r'\1', css)
    # Remove semicolon before closing brace
    css = re.sub(r';\}', '}', css)
    return css.strip()


def minify_js(js_text: str) -> str:
    """Minifies JS content by removing comments and unneeded whitespace."""
    if not js_text:
        return ""
    lines = js_text.splitlines()
    minified_lines = []
    in_multiline_comment = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        
        # Handle multi-line comment start/end
        if in_multiline_comment:
            if "*/" in stripped:
                in_multiline_comment = False
                stripped = stripped.split("*/", 1)[1].strip()
            else:
                continue

        if stripped.startswith("/*"):
            if "*/" in stripped:
                stripped = stripped.rsplit("*/", 1)[1].strip()
            else:
                in_multiline_comment = True
                continue

        if stripped.startswith("//") and not (":" in stripped and "http" in stripped):
            continue

        # Strip inline trailing comments if not part of string literal
        if " //" in stripped and not ('"' in stripped or "'" in stripped or '`' in stripped):
            stripped = stripped.split(" //")[0].strip()

        if stripped:
            minified_lines.append(stripped)

    result = "\n".join(minified_lines)
    # Basic token whitespace cleanup
    result = re.sub(r'\n+', '\n', result)
    return result


def build_and_minify_assets(web_dir: Path = None) -> dict:
    """Processes static assets in web_dir, writing .min.css and .min.js files."""
    target_dir = web_dir or WEB_DIR
    target_dir = Path(target_dir)

    results = {
        "files_processed": 0,
        "total_original_bytes": 0,
        "total_minified_bytes": 0,
        "saved_bytes": 0,
        "compression_pct": 0.0,
        "details": {}
    }

    if not target_dir.exists():
        return results

    # Process CSS
    css_file = target_dir / "style.css"
    if css_file.exists():
        orig_css = css_file.read_text(encoding="utf-8")
        min_css = minify_css(orig_css)
        out_file = target_dir / "style.min.css"
        out_file.write_text(min_css, encoding="utf-8")

        orig_len = len(orig_css.encode("utf-8"))
        min_len = len(min_css.encode("utf-8"))
        results["files_processed"] += 1
        results["total_original_bytes"] += orig_len
        results["total_minified_bytes"] += min_len
        results["details"]["style.css"] = {
            "original_bytes": orig_len,
            "minified_bytes": min_len,
            "reduction_pct": round((1 - min_len / orig_len) * 100, 2) if orig_len > 0 else 0.0,
            "output_file": str(out_file)
        }

    # Process JS
    js_file = target_dir / "app.js"
    if js_file.exists():
        orig_js = js_file.read_text(encoding="utf-8")
        min_js = minify_js(orig_js)
        out_file = target_dir / "app.min.js"
        out_file.write_text(min_js, encoding="utf-8")

        orig_len = len(orig_js.encode("utf-8"))
        min_len = len(min_js.encode("utf-8"))
        results["files_processed"] += 1
        results["total_original_bytes"] += orig_len
        results["total_minified_bytes"] += min_len
        results["details"]["app.js"] = {
            "original_bytes": orig_len,
            "minified_bytes": min_len,
            "reduction_pct": round((1 - min_len / orig_len) * 100, 2) if orig_len > 0 else 0.0,
            "output_file": str(out_file)
        }

    css_orig = results["details"].get("style.css", {}).get("original_bytes", 0)
    css_min = results["details"].get("style.css", {}).get("minified_bytes", 0)
    js_orig = results["details"].get("app.js", {}).get("original_bytes", 0)
    js_min = results["details"].get("app.js", {}).get("minified_bytes", 0)

    results["style_css_orig_bytes"] = css_orig
    results["style_css_min_bytes"] = css_min
    results["app_js_orig_bytes"] = js_orig
    results["app_js_min_bytes"] = js_min
    results["style_min_file"] = str(target_dir / "style.min.css")
    results["app_min_file"] = str(target_dir / "app.min.js")
    results["css_savings_pct"] = round((1 - css_min / css_orig) * 100, 2) if css_orig > 0 else 0.0
    results["js_savings_pct"] = round((1 - js_min / js_orig) * 100, 2) if js_orig > 0 else 0.0

    return results


build_minified_assets = build_and_minify_assets


if __name__ == "__main__":
    res = build_and_minify_assets()
    print("Static Asset Minification Results:")
    print(json.dumps(res, indent=2))
