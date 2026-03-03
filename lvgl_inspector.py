"""
LVGL Application Structure Inspector
- OpenCV-based screenshot capture (replaces pywinauto)
- Linux-native & QEMU/VNC compatible
- Deep object discovery with maximum property extraction
"""

import cv2
import numpy as np
import subprocess
import time
import os
import json
from typing import Optional, Any
from dataclasses import dataclass, field
from robot.api.deco import keyword


# ──────────────────────────────────────────────
# Screenshot / Display backends
# ──────────────────────────────────────────────

class ScreenshotBackend:
    """Selects the right capture method depending on environment."""

    @staticmethod
    def capture_x11(display=":0") -> np.ndarray:
        """Capture X11 display via xwd + OpenCV (no extra deps)."""
        cmd = ["xwd", "-root", "-silent", "-display", display]
        proc = subprocess.run(cmd, capture_output=True)
        if proc.returncode != 0:
            raise RuntimeError(f"xwd failed: {proc.stderr.decode()}")
        xwd = proc.stdout

        # Convert XWD → PNG via ImageMagick convert, then decode with OpenCV
        convert = subprocess.run(
            ["convert", "xwd:-", "png:-"],
            input=xwd, capture_output=True
        )
        arr = np.frombuffer(convert.stdout, np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)

    @staticmethod
    def capture_vnc(host="127.0.0.1", port=5900, password="") -> np.ndarray:
        """
        Capture a single frame from a VNC server (QEMU default port 5900).
        Uses vncsnapshot CLI tool if available, otherwise falls back to
        a minimal RFB handshake implemented here.
        """
        # Try vncsnapshot first (apt install vncsnapshot)
        tmp = "/tmp/_lvgl_vnc_cap.png"
        pwd_flag = ["-passwd", password] if password else []
        result = subprocess.run(
            ["vncsnapshot"] + pwd_flag + [f"{host}:{port - 5900}", tmp],
            capture_output=True
        )
        if result.returncode == 0 and os.path.exists(tmp):
            img = cv2.imread(tmp)
            os.remove(tmp)
            return img

        # Fallback: use ffmpeg to grab one frame from VNC
        result = subprocess.run([
            "ffmpeg", "-y",
            "-f", "vnc", "-i", f"{host}:{port}",
            "-frames:v", "1", "-f", "image2", tmp
        ], capture_output=True, timeout=10)
        if result.returncode == 0 and os.path.exists(tmp):
            img = cv2.imread(tmp)
            os.remove(tmp)
            return img

        raise RuntimeError(
            "VNC capture failed. Install 'vncsnapshot' or 'ffmpeg' with VNC support."
        )

    @staticmethod
    def capture_framebuffer(device="/dev/fb0", width=800, height=480) -> np.ndarray:
        """Read directly from Linux framebuffer (embedded/QEMU console)."""
        with open(device, "rb") as f:
            raw = f.read(width * height * 4)  # BGRA 32-bit
        frame = np.frombuffer(raw, dtype=np.uint8).reshape((height, width, 4))
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

    @staticmethod
    def save_annotated(img: np.ndarray, path="/tmp/lvgl_snapshot.png"):
        cv2.imwrite(path, img)
        print(f"   📸 Snapshot saved: {path}")


# ──────────────────────────────────────────────
# Property extraction helpers
# ──────────────────────────────────────────────

# All known LVGL widget types (lv_ prefix stripped for matching)
LVGL_WIDGET_TYPES = [
    "obj", "btn", "label", "img", "line", "table", "bar", "slider",
    "switch", "checkbox", "dropdown", "roller", "textarea", "canvas",
    "arc", "meter", "chart", "spinbox", "list", "menu", "msgbox",
    "tileview", "tabview", "win", "calendar", "colorwheel", "imgbtn",
    "keyboard", "led", "span", "spinbox", "animimg",
]

# All LVGL states that can be queried
LVGL_STATES = [
    "checked", "focused", "focused_key", "edited",
    "hovered", "pressed", "scrolled", "disabled",
]

# Extra props to probe beyond the standard ones
EXTRA_PROPS = [
    "text", "value", "min_value", "max_value", "range_min", "range_max",
    "checked", "disabled", "hidden", "visible", "opacity",
    "x", "y", "width", "height",
    "bg_color", "text_color", "border_color",
    "border_width", "radius", "pad_top", "pad_bottom", "pad_left", "pad_right",
    "align", "flex_flow", "flex_grow",
    "scroll_x", "scroll_y", "scrollbar_mode",
    "anim_time", "anim_speed",
    "src",          # image source
    "symbol",       # label symbol
    "placeholder",  # textarea
    "options",      # dropdown / roller
    "row_count", "col_count",  # table
    "angle", "zoom",            # image transform
    "bar_value", "start_value", # arc / bar
    "mode",
    "dir",
    "event_count",
]


def _safe_get(obj, attr, default=None):
    try:
        val = getattr(obj, attr, default)
        return val() if callable(val) else val
    except Exception:
        return default


def _extract_all_props(node) -> dict:
    """Extract every discoverable property from an LVGL node."""
    props = {}

    # Standard props object
    props_obj = _safe_get(node, "props")
    if props_obj:
        for attr in dir(props_obj):
            if attr.startswith("_"):
                continue
            val = _safe_get(props_obj, attr)
            if val is not None and not callable(val):
                props[attr] = val

    # Probe extra known props directly on node
    for prop in EXTRA_PROPS:
        if prop not in props:
            val = _safe_get(node, prop)
            if val is not None:
                props[prop] = val

    # States
    states = {}
    for state in LVGL_STATES:
        val = _safe_get(node, f"is_{state}", _safe_get(node, state))
        if val is not None:
            states[state] = val
    if states:
        props["_states"] = states

    # Geometry (separate attempt in case not in props)
    for geo in ("x", "y", "width", "height", "abs_x", "abs_y"):
        if geo not in props:
            val = _safe_get(node, geo)
            if val is not None:
                props[geo] = val

    # Style list
    style_count = _safe_get(node, "style_count", _safe_get(node, "get_style_count"))
    if style_count:
        props["_style_count"] = style_count

    # Event list
    event_count = _safe_get(node, "event_count", _safe_get(node, "get_event_count"))
    if event_count:
        props["_event_count"] = event_count

    # propsType / widget type hints
    for hint in ("propsType", "widget_type", "type", "class_id"):
        val = _safe_get(node, hint)
        if val is not None:
            props[f"_{hint}"] = val

    return {k: v for k, v in props.items() if v != "" and v is not None}


# ──────────────────────────────────────────────
# Node discovery — scan EVERYTHING
# ──────────────────────────────────────────────

# IDs to probe in addition to the standard root traversal
KNOWN_ROOT_IDS = [
    "root", "screen", "lv_screen_active", "main",
    "app", "home", "base", "bg", "background",
]

# Common structural IDs to always probe
STRUCTURAL_IDS = [
    "header", "footer", "sidebar", "navbar", "statusbar",
    "top-bar", "bottom-bar", "overlay", "modal", "popup",
    "dialog", "toast", "snackbar", "drawer",
    "dashboard", "content", "body", "main-content",
]


# ──────────────────────────────────────────────
# Robot Framework Keyword class
# ──────────────────────────────────────────────

class LVGLInspector:

    def _make_client(self, ip="192.168.0.10", port=8080,
                     topic="receive-test-queries",
                     user="test-client", pwd="test-client"):
        from your_client_module import Client   # ← replace with your import
        return Client(ip=ip, port=port, test_topic=topic,
                      username=user, password=pwd)

    # ------------------------------------------------------------------
    @keyword("LVGL Application Structure")
    def lvgl_application_structure(
        self,
        element="root",
        max_depth=None,
        show_props=True,
        show_text=True,
        # connection
        ip="192.168.0.10",
        port=8080,
        # screenshot settings
        capture="none",          # none | x11 | vnc | framebuffer
        vnc_host="127.0.0.1",
        vnc_port=5900,
        fb_device="/dev/fb0",
        snapshot_path="/tmp/lvgl_snapshot.png",
        # discovery settings
        deep_scan=True,
        scan_hidden=True,
        scan_extra_roots=True,
    ):
        """
        Prints the full LVGL application tree with maximum object discovery.

        Args:
            element:          Starting element ID (default: 'root')
            max_depth:        Max traversal depth (None = unlimited)
            show_props:       Show all extracted properties
            show_text:        Show text content
            ip / port:        LVGL test server address
            capture:          Screenshot backend — none | x11 | vnc | framebuffer
            vnc_host/port:    VNC server address (for QEMU)
            fb_device:        Linux framebuffer device
            snapshot_path:    Where to save the annotated screenshot
            deep_scan:        Also probe structural IDs and collect orphan nodes
            scan_hidden:      Include hidden / invisible nodes
            scan_extra_roots: Try alternative root IDs if primary not found
        """
        client = self._make_client(ip=ip, port=port)

        # ── Optional screenshot ──────────────────────────────────────
        screenshot = None
        if capture == "x11":
            screenshot = ScreenshotBackend.capture_x11()
        elif capture == "vnc":
            screenshot = ScreenshotBackend.capture_vnc(vnc_host, vnc_port)
        elif capture == "framebuffer":
            screenshot = ScreenshotBackend.capture_framebuffer(fb_device)

        if screenshot is not None:
            ScreenshotBackend.save_annotated(screenshot, snapshot_path)

        # ── Resolve root ─────────────────────────────────────────────
        root = None
        ids_to_try = [element]
        if scan_extra_roots:
            ids_to_try += [i for i in KNOWN_ROOT_IDS if i != element]

        for eid in ids_to_try:
            try:
                root = client.get_by_id(eid)
                if root is not None:
                    element = eid
                    break
            except Exception:
                continue

        if root is None:
            print(f"⚠️  Could not resolve any root element. Tried: {ids_to_try}")
            return

        print(f"\n{'='*80}")
        print(f"🌳 LVGL APPLICATION TREE  —  root: '{element}'")
        print(f"{'='*80}")

        visited_uids = set()
        total = [0]

        self._print_tree_visual(
            root, client=client,
            max_depth=max_depth, show_props=show_props, show_text=show_text,
            scan_hidden=scan_hidden, visited=visited_uids, counter=total,
        )

        # ── Deep scan: probe structural IDs not yet seen ──────────────
        if deep_scan:
            extra_found = []
            all_probe_ids = STRUCTURAL_IDS + [
                f"{element}-{suffix}"
                for suffix in ["overlay", "popup", "modal", "loading", "error"]
            ]
            for eid in all_probe_ids:
                if eid in visited_uids:
                    continue
                try:
                    node = client.get_by_id(eid)
                    if node is not None:
                        extra_found.append((eid, node))
                except Exception:
                    pass

            if extra_found:
                print(f"\n{'─'*60}")
                print(f"🔍 DEEP SCAN — {len(extra_found)} extra nodes found outside main tree")
                print(f"{'─'*60}")
                for eid, node in extra_found:
                    self._print_tree_visual(
                        node, client=client,
                        max_depth=max_depth, show_props=show_props, show_text=show_text,
                        scan_hidden=scan_hidden, visited=visited_uids, counter=total,
                    )

        print(f"{'='*80}")
        print(f"📊 Total nodes discovered: {total[0]}")
        print(f"{'='*80}\n")

        # ── Annotate screenshot with node count ───────────────────────
        if screenshot is not None:
            annotated = screenshot.copy()
            cv2.putText(
                annotated,
                f"LVGL nodes: {total[0]}",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1,
                (0, 255, 0), 2, cv2.LINE_AA
            )
            cv2.imwrite(snapshot_path, annotated)

    # ------------------------------------------------------------------
    def _print_tree_visual(
        self, node, client=None,
        indent=0, max_depth=None, current_depth=0,
        show_props=True, show_text=True,
        scan_hidden=True,
        is_last=True, parent_prefix="",
        visited: Optional[set] = None,
        counter: Optional[list] = None,
    ):
        """Recursive pretty-printer with maximum property discovery."""

        if max_depth is not None and current_depth > max_depth:
            return
        if visited is None:
            visited = set()
        if counter is None:
            counter = [0]

        uid = _safe_get(node, "uid", "NO_UID")

        # Cycle guard
        if uid in visited:
            print(f"{parent_prefix}   ⚠️  [cycle detected: {uid}]")
            return
        visited.add(uid)
        counter[0] += 1

        class_name = _safe_get(node, "className", "")

        # Skip hidden unless requested
        is_hidden = _safe_get(node, "hidden", False) or _safe_get(node, "is_hidden", False)
        hidden_tag = " 👁️‍🗨️[hidden]" if is_hidden else ""
        if is_hidden and not scan_hidden:
            return

        # ── Tree connectors ───────────────────────────────────────────
        if indent == 0:
            connector, prefix, next_prefix = "🏠 ", "", ""
        else:
            connector = "└── " if is_last else "├── "
            prefix = parent_prefix
            next_prefix = parent_prefix + ("    " if is_last else "│   ")

        # ── Icon by UID keywords ──────────────────────────────────────
        icon_map = {
            "sidebar":    "📱", "dashboard": "📊", "top-bar":   "🔝",
            "bottom":     "⬇️ ", "menu":      "📋", "button":    "🔘",
            "btn":        "🔘", "text":      "📄", "label":     "🏷️ ",
            "image":      "🖼️ ", "img":       "🖼️ ", "container": "📦",
            "screen":     "🖥️ ", "overlay":   "🔲", "modal":     "🪟",
            "input":      "⌨️ ", "textarea":  "✏️ ", "switch":    "🔀",
            "slider":     "🎚️ ", "bar":       "📊", "arc":       "🌀",
            "chart":      "📈", "table":     "🗃️ ", "list":      "📋",
            "scroll":     "📜", "tab":       "🗂️ ", "calendar":  "📅",
            "keyboard":   "⌨️ ", "led":       "💡", "roller":    "🎰",
            "dropdown":   "🔽", "checkbox":  "☑️ ", "spinner":   "⏳",
            "header":     "🔝", "footer":    "⬇️ ", "nav":       "🧭",
            "popup":      "💬", "toast":     "🍞", "loading":   "⏳",
            "icon":       "🔣", "logo":      "🏷️ ", "card":      "🃏",
        }
        uid_lower = str(uid).lower()
        element_icon = next(
            (icon for key, icon in icon_map.items() if key in uid_lower), "◼️ "
        )

        class_display = f"  [cls: {class_name}]" if class_name and class_name != "None" else ""
        print(f"{prefix}{connector}{element_icon} {uid}{class_display}{hidden_tag}")

        # ── Properties ───────────────────────────────────────────────
        if show_props or show_text:
            all_props = _extract_all_props(node)
            prop_prefix = next_prefix + "    "

            if show_text:
                for key in ("text", "label", "placeholder", "symbol", "src", "options"):
                    val = all_props.get(key)
                    if val:
                        print(f"{prop_prefix}📝 {key}: '{val}'")

            if show_props and all_props:
                # Geometry block
                geo_keys = [k for k in ("x", "y", "width", "height", "abs_x", "abs_y") if k in all_props]
                if geo_keys:
                    geo_str = "  ".join(f"{k}={all_props[k]}" for k in geo_keys)
                    print(f"{prop_prefix}📐 geometry: {geo_str}")

                # States block
                states = all_props.get("_states", {})
                active_states = [s for s, v in states.items() if v]
                if active_states:
                    print(f"{prop_prefix}🔵 states: {', '.join(active_states)}")

                # Visual properties
                visual_keys = [k for k in all_props if any(
                    k.startswith(p) for p in ("bg_", "text_", "border_", "pad_", "radius", "opacity")
                )]
                if visual_keys:
                    vis_str = "  ".join(f"{k}={all_props[k]}" for k in visual_keys[:8])
                    print(f"{prop_prefix}🎨 style: {vis_str}")

                # Functional properties
                func_keys = [k for k in all_props if k not in geo_keys + visual_keys + ["_states"]
                             and not k.startswith("_") and k not in ("text", "label", "placeholder",
                             "symbol", "src", "options", "x", "y", "width", "height")]
                if func_keys:
                    func_str = "  ".join(f"{k}={all_props[k]}" for k in func_keys[:10])
                    print(f"{prop_prefix}🔧 props: {func_str}")

                # Meta (propsType, event count, style count)
                for meta_key in ("_propsType", "_widget_type", "_type", "_event_count", "_style_count"):
                    if meta_key in all_props:
                        label = meta_key.lstrip("_")
                        print(f"{prop_prefix}ℹ️  {label}: {all_props[meta_key]}")

        # ── Children ─────────────────────────────────────────────────
        children = _safe_get(node, "children", []) or []

        # Some nodes expose children as a method
        if callable(children):
            try:
                children = children()
            except Exception:
                children = []

        child_count = len(children)

        if child_count > 0:
            if current_depth == 0:
                print(f"{next_prefix}   👥 children: {child_count}")
            for i, child in enumerate(children):
                self._print_tree_visual(
                    child, client=client,
                    indent=indent + 1,
                    max_depth=max_depth,
                    current_depth=current_depth + 1,
                    show_props=show_props,
                    show_text=show_text,
                    scan_hidden=scan_hidden,
                    is_last=(i == child_count - 1),
                    parent_prefix=next_prefix,
                    visited=visited,
                    counter=counter,
                )

    # ------------------------------------------------------------------
    @keyword("LVGL Screenshot")
    def lvgl_screenshot(
        self,
        path="/tmp/lvgl_snapshot.png",
        capture="vnc",
        vnc_host="127.0.0.1",
        vnc_port=5900,
        fb_device="/dev/fb0",
    ):
        """
        Capture a screenshot of the LVGL app.
        capture: vnc | x11 | framebuffer
        """
        if capture == "vnc":
            img = ScreenshotBackend.capture_vnc(vnc_host, vnc_port)
        elif capture == "x11":
            img = ScreenshotBackend.capture_x11()
        else:
            img = ScreenshotBackend.capture_framebuffer(fb_device)

        ScreenshotBackend.save_annotated(img, path)
        return path

    # ------------------------------------------------------------------
    @keyword("LVGL Find Element By Visual")
    def lvgl_find_element_by_visual(
        self,
        template_path: str,
        capture="vnc",
        vnc_host="127.0.0.1",
        vnc_port=5900,
        threshold=0.85,
    ) -> Optional[tuple]:
        """
        Find a UI element by template matching using OpenCV.
        Returns (x, y, w, h) of the best match, or None.
        """
        if capture == "vnc":
            screen = ScreenshotBackend.capture_vnc(vnc_host, vnc_port)
        else:
            screen = ScreenshotBackend.capture_x11()

        template = cv2.imread(template_path, cv2.IMREAD_COLOR)
        if template is None:
            raise FileNotFoundError(f"Template not found: {template_path}")

        result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= threshold:
            h, w = template.shape[:2]
            x, y = max_loc
            print(f"   ✅ Template matched at ({x},{y}) size={w}×{h}  confidence={max_val:.2f}")
            return (x, y, w, h)
        else:
            print(f"   ❌ Template not found (best={max_val:.2f} < threshold={threshold})")
            return None

    # ------------------------------------------------------------------
    @keyword("LVGL Diff Screenshots")
    def lvgl_diff_screenshots(
        self,
        img1_path: str,
        img2_path: str,
        output_path="/tmp/lvgl_diff.png",
        threshold=30,
    ) -> int:
        """
        Compare two LVGL screenshots with OpenCV and highlight differences.
        Returns the number of differing pixels.
        """
        img1 = cv2.imread(img1_path)
        img2 = cv2.imread(img2_path)
        if img1 is None or img2 is None:
            raise FileNotFoundError("One or both images not found.")

        # Resize if needed
        if img1.shape != img2.shape:
            img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))

        diff = cv2.absdiff(img1, img2)
        gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        annotated = img1.copy()
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 0, 255), 2)

        cv2.imwrite(output_path, annotated)
        pixel_diff = int(np.count_nonzero(mask))
        print(f"   🔍 Diff pixels: {pixel_diff}  —  saved to {output_path}")
        return pixel_diff