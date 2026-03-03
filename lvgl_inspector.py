"""
LVGL inspector backed by pylvgl_selectors.

This module exposes:
- ScreenshotBackend: screenshot utilities for x11/vnc/framebuffer
- LVGLInspector: builds an inspectable tree with locators based on
  pylvgl_selectors.Client selectors.
"""

import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

try:
    from robot.api.deco import keyword
except Exception:
    def keyword(_name=None):
        def _decorator(func):
            return func
        return _decorator


def _import_pylvgl_client():
    try:
        from pylvgl_selectors.client import Client  # type: ignore
        return Client
    except Exception:
        local_src = os.path.join(
            os.path.dirname(__file__),
            "pylvgl_selectors-0.0.1",
            "pylvgl_selectors-0.0.1",
            "src",
        )
        if os.path.isdir(local_src) and local_src not in sys.path:
            sys.path.append(local_src)
        from pylvgl_selectors.client import Client  # type: ignore
        return Client


def _safe_get(obj: Any, attr: str, default: Any = None) -> Any:
    try:
        value = getattr(obj, attr, default)
        return value() if callable(value) else value
    except Exception:
        return default


def _decode_bytes(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8")
        except Exception:
            return str(value)
    return value


def _to_primitive(value: Any, depth: int = 0, max_depth: int = 3) -> Any:
    if depth > max_depth:
        return str(value)
    value = _decode_bytes(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_to_primitive(v, depth + 1, max_depth) for v in value]
    if isinstance(value, tuple):
        return [_to_primitive(v, depth + 1, max_depth) for v in value]
    if isinstance(value, dict):
        return {str(k): _to_primitive(v, depth + 1, max_depth) for k, v in value.items()}
    if hasattr(value, "__dict__"):
        out = {}
        for key, item in value.__dict__.items():
            if key.startswith("_"):
                continue
            if key == "children":
                continue
            out[key] = _to_primitive(item, depth + 1, max_depth)
        return out
    return str(value)


class ScreenshotBackend:
    @staticmethod
    def _read_image_and_cleanup(path: str) -> np.ndarray:
        image = cv2.imread(path)
        try:
            os.remove(path)
        except Exception:
            pass
        if image is None:
            raise RuntimeError(f"Failed to read screenshot image at {path}.")
        return image

    @staticmethod
    def capture_qemu_monitor(host="127.0.0.1", port=55555, timeout=4) -> np.ndarray:
        ppm_path = os.path.join(tempfile.gettempdir(), "_qemu_monitor_screendump.ppm")
        try:
            sock = socket.create_connection((host, int(port)), timeout=timeout)
        except Exception as exc:
            raise RuntimeError(f"Could not connect to QEMU monitor at {host}:{port}: {exc}") from exc

        try:
            sock.settimeout(0.5)
            try:
                sock.recv(4096)
            except Exception:
                pass
            cmd = f"screendump {ppm_path}\n".encode("utf-8")
            sock.sendall(cmd)
            end_time = time.time() + timeout
            while time.time() < end_time:
                if os.path.exists(ppm_path) and os.path.getsize(ppm_path) > 0:
                    return ScreenshotBackend._read_image_and_cleanup(ppm_path)
                time.sleep(0.1)
            raise RuntimeError("Monitor screendump command timed out.")
        finally:
            try:
                sock.close()
            except Exception:
                pass

    @staticmethod
    def _qmp_send(sock: socket.socket, payload: Dict[str, Any], timeout=2) -> Dict[str, Any]:
        sock.settimeout(timeout)
        sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        raw = sock.recv(8192).decode("utf-8", errors="ignore")
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except Exception:
                continue
            if "return" in data or "error" in data:
                return data
        return {}

    @staticmethod
    def capture_qemu_qmp(socket_path="/tmp/qemu.sock", timeout=4) -> np.ndarray:
        ppm_path = os.path.join(tempfile.gettempdir(), "_qemu_qmp_screendump.ppm")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(timeout)
            sock.connect(socket_path)
            try:
                sock.recv(4096)
            except Exception:
                pass
            ScreenshotBackend._qmp_send(sock, {"execute": "qmp_capabilities"})
            resp = ScreenshotBackend._qmp_send(
                sock, {"execute": "screendump", "arguments": {"filename": ppm_path}}
            )
            if "error" in resp:
                raise RuntimeError(f"QMP screendump error: {resp['error']}")
            end_time = time.time() + timeout
            while time.time() < end_time:
                if os.path.exists(ppm_path) and os.path.getsize(ppm_path) > 0:
                    return ScreenshotBackend._read_image_and_cleanup(ppm_path)
                time.sleep(0.1)
            raise RuntimeError("QMP screendump timed out.")
        except Exception as exc:
            raise RuntimeError(f"QMP capture failed at {socket_path}: {exc}") from exc
        finally:
            try:
                sock.close()
            except Exception:
                pass

    @staticmethod
    def capture_x11(display=":0") -> np.ndarray:
        cmd = ["xwd", "-root", "-silent", "-display", display]
        proc = subprocess.run(cmd, capture_output=True)
        if proc.returncode != 0:
            raise RuntimeError(f"xwd failed: {proc.stderr.decode()}")
        xwd = proc.stdout
        convert = subprocess.run(["convert", "xwd:-", "png:-"], input=xwd, capture_output=True)
        arr = np.frombuffer(convert.stdout, np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError("Failed to decode X11 screenshot.")
        return image

    @staticmethod
    def capture_vnc(host="192.168.0.10", port=5900, password="") -> np.ndarray:
        tmp = os.path.join(tempfile.gettempdir(), "_lvgl_vnc_cap.png")
        pwd_flag = ["-passwd", password] if password else []
        vncsnapshot_error = None
        try:
            result = subprocess.run(
                ["vncsnapshot"] + pwd_flag + [f"{host}:{port - 5900}", tmp],
                capture_output=True,
            )
            if result.returncode == 0 and os.path.exists(tmp):
                image = cv2.imread(tmp)
                os.remove(tmp)
                if image is None:
                    raise RuntimeError("Failed to read VNC snapshot image.")
                return image
            vncsnapshot_error = result.stderr.decode(errors="ignore")
        except FileNotFoundError:
            vncsnapshot_error = "vncsnapshot not installed"

        ffmpeg_error = None
        try:
            result = subprocess.run(
                ["ffmpeg", "-y", "-f", "vnc", "-i", f"{host}:{port}", "-frames:v", "1", "-f", "image2", tmp],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0 and os.path.exists(tmp):
                image = cv2.imread(tmp)
                os.remove(tmp)
                if image is None:
                    raise RuntimeError("Failed to read ffmpeg VNC capture image.")
                return image
            ffmpeg_error = result.stderr.decode(errors="ignore")
        except FileNotFoundError:
            ffmpeg_error = "ffmpeg not installed"

        ffmpeg_protocol_error = None
        try:
            vnc_url = f"vnc://{host}:{port}"
            if password:
                vnc_url = f"vnc://:{password}@{host}:{port}"
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", vnc_url, "-frames:v", "1", tmp],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0 and os.path.exists(tmp):
                image = cv2.imread(tmp)
                os.remove(tmp)
                if image is None:
                    raise RuntimeError("Failed to read ffmpeg protocol VNC capture image.")
                return image
            ffmpeg_protocol_error = result.stderr.decode(errors="ignore")
        except FileNotFoundError:
            ffmpeg_protocol_error = "ffmpeg not installed"

        raise RuntimeError(
            "VNC capture failed "
            f"(vncsnapshot: {vncsnapshot_error}; ffmpeg demuxer mode: {ffmpeg_error}; "
            f"ffmpeg protocol mode: {ffmpeg_protocol_error}). "
            "Install vncsnapshot/ffmpeg or select capture method 'none'."
        )

    @staticmethod
    def capture_framebuffer(device="/dev/fb0", width=800, height=480) -> np.ndarray:
        with open(device, "rb") as f:
            raw = f.read(width * height * 4)
        frame = np.frombuffer(raw, dtype=np.uint8).reshape((height, width, 4))
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

    @staticmethod
    def save_annotated(img: np.ndarray, path="/tmp/lvgl_snapshot.png"):
        cv2.imwrite(path, img)


class LVGLInspector:
    ROOT_CANDIDATES = ["root", "screen", "lv_screen_active", "main", "app", "home"]

    def _make_client(
        self,
        ip="192.168.0.10",
        port=8080,
        topic="receive-test-queries",
        user="test-client",
        pwd="test-client",
    ):
        client_cls = _import_pylvgl_client()
        return client_cls(ip=ip, port=port, test_topic=topic, username=user, password=pwd)

    def _resolve_root(self, client, element: str, scan_extra_roots: bool):
        candidates = [element]
        if scan_extra_roots:
            candidates.extend([c for c in self.ROOT_CANDIDATES if c != element])
        for candidate in candidates:
            try:
                root = client.get_by_id(candidate)
                if root is not None:
                    return root, candidate
            except Exception:
                continue
        return None, None

    def _make_locators(self, uid: str, class_name: str, text: str) -> Dict[str, str]:
        locators: Dict[str, str] = {}
        uid_q = uid.replace("'", "\\'")
        class_q = class_name.replace("'", "\\'")
        text_q = text.replace("'", "\\'")
        if uid:
            locators["by_id"] = f"client.get_by_id('{uid_q}')"
            locators["trigger_click"] = f"client.trigger_handler('{uid_q}', 'onClick')"
        if class_name:
            locators["by_classname"] = f"client.get_by_classname('{class_q}')"
        if text:
            locators["by_text"] = f"client.get_by_text('{text_q}')"
        return locators

    def _node_id(self, uid: str, class_name: str, idx: int) -> str:
        key = f"{uid}|{class_name}|{idx}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:10]

    def _instance_to_tree(self, instance: Any, idx_counter: List[int], parent_title: str = "") -> Dict[str, Any]:
        idx = idx_counter[0]
        idx_counter[0] += 1

        uid = _safe_get(instance, "uid", "") or ""
        class_name = _safe_get(instance, "className", "") or ""
        props = _to_primitive(_safe_get(instance, "props", None))
        if not isinstance(props, dict):
            props = {}
        text = props.get("text") or props.get("label") or props.get("value") or ""

        x = int(props.get("x") or props.get("abs_x") or 0)
        y = int(props.get("y") or props.get("abs_y") or 0)
        width = int(props.get("width") or 0)
        height = int(props.get("height") or 0)

        title = str(text or uid or class_name or f"lvgl_node_{idx}")
        locators = self._make_locators(str(uid), str(class_name), str(text))

        raw_children = _safe_get(instance, "children", []) or []
        children = [
            self._instance_to_tree(child, idx_counter, parent_title=title)
            for child in raw_children
            if child is not None
        ]

        return {
            "idx": idx,
            "parent_idx": None,
            "rect": {
                "Left": x,
                "Top": y,
                "Right": x + max(width, 0),
                "Bottom": y + max(height, 0),
            },
            "center": {
                "X": x + max(width, 0) // 2,
                "Y": y + max(height, 0) // 2,
            },
            "attributes": {
                "title": title,
                "auto_id": uid,
                "control_type": class_name or "LVGL Object",
                "found_index": 0,
                "parent": {"title": parent_title} if parent_title else {},
                "locators": locators,
                "selector_usage": list(locators.values()),
                "props": props,
            },
            "node_id": self._node_id(str(uid), str(class_name), idx),
            "children": children,
        }

    def _set_parent_indexes(self, node: Dict[str, Any], parent_idx: Optional[int] = None):
        node["parent_idx"] = parent_idx
        for child in node.get("children", []):
            self._set_parent_indexes(child, node["idx"])

    @keyword("LVGL Application Structure")
    def lvgl_application_structure(
        self,
        element="root",
        max_depth=None,
        show_props=True,
        show_text=True,
        ip="192.168.0.10",
        port=8080,
        topic="receive-test-queries",
        username="test-client",
        password="test-client",
        capture="none",
        vnc_host="192.168.0.10",
        vnc_port=5900,
        fb_device="/dev/fb0",
        snapshot_path="/tmp/lvgl_snapshot.png",
        deep_scan=True,
        scan_hidden=True,
        scan_extra_roots=True,
    ):
        del max_depth, show_props, show_text, deep_scan, scan_hidden

        client = self._make_client(ip=ip, port=port, topic=topic, user=username, pwd=password)
        try:
            if capture == "x11":
                ScreenshotBackend.save_annotated(ScreenshotBackend.capture_x11(), snapshot_path)
            elif capture == "vnc":
                ScreenshotBackend.save_annotated(ScreenshotBackend.capture_vnc(vnc_host, vnc_port), snapshot_path)
            elif capture == "framebuffer":
                ScreenshotBackend.save_annotated(
                    ScreenshotBackend.capture_framebuffer(fb_device),
                    snapshot_path,
                )

            root, resolved_root = self._resolve_root(client, element, scan_extra_roots)
            if root is None:
                raise ValueError(f"Could not resolve LVGL root. Tried '{element}' and known alternatives.")

            tree = self._instance_to_tree(root, idx_counter=[0], parent_title="")
            self._set_parent_indexes(tree, None)
            tree["attributes"]["resolved_root"] = resolved_root
            return tree
        finally:
            try:
                client.stop()
            except Exception:
                pass

    @keyword("LVGL Screenshot")
    def lvgl_screenshot(
        self,
        path="/tmp/lvgl_snapshot.png",
        capture="vnc",
        vnc_host="192.168.0.10",
        vnc_port=5900,
        fb_device="/dev/fb0",
    ):
        if capture == "vnc":
            img = ScreenshotBackend.capture_vnc(vnc_host, vnc_port)
        elif capture == "x11":
            img = ScreenshotBackend.capture_x11()
        else:
            img = ScreenshotBackend.capture_framebuffer(fb_device)
        ScreenshotBackend.save_annotated(img, path)
        return path

    @keyword("LVGL Find Element By Visual")
    def lvgl_find_element_by_visual(
        self,
        template_path: str,
        capture="vnc",
        vnc_host="192.168.0.10",
        vnc_port=5900,
        threshold=0.85,
    ) -> Optional[tuple]:
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
            return (x, y, w, h)
        return None

    @keyword("LVGL Diff Screenshots")
    def lvgl_diff_screenshots(
        self,
        img1_path: str,
        img2_path: str,
        output_path="/tmp/lvgl_diff.png",
        threshold=30,
    ) -> int:
        img1 = cv2.imread(img1_path)
        img2 = cv2.imread(img2_path)
        if img1 is None or img2 is None:
            raise FileNotFoundError("One or both images not found.")

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
        return int(np.count_nonzero(mask))
