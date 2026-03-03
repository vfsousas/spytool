const state = {
    tree: null,
    nodeDictionary: {},
    activeNodeId: null,
    scaleX: 1,
    scaleY: 1,
    windowRect: null,
    inspectorType: "opencv",
    treeExpandedState: {},
};

const TREE_EXPANDED_KEY = "tree_expanded_state";

// ─────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────

function loadExpandedState() {
    try {
        var raw = localStorage.getItem(TREE_EXPANDED_KEY);
        state.treeExpandedState = raw ? JSON.parse(raw) : {};
    } catch (_) {
        state.treeExpandedState = {};
    }
}

function saveExpandedState() {
    try {
        localStorage.setItem(TREE_EXPANDED_KEY, JSON.stringify(state.treeExpandedState));
    } catch (_) {}
}

function formatTime(milliseconds) {
    var seconds = Math.floor(milliseconds / 1000);
    var h = Math.floor(seconds / 3600);
    var m = Math.floor((seconds % 3600) / 60);
    var s = seconds % 60;
    return `${pad(h)}:${pad(m)}:${pad(s)}`;
}

function pad(v) { return v < 10 ? '0' + v : v; }

function setStatus(text, type) {
    var el = document.getElementById("status");
    el.textContent = text;
    el.dataset.type = type || "info";
}

function setLoading(isLoading, text) {
    var indicator = document.getElementById("loadingIndicator");
    var loadingText = document.getElementById("loadingText");
    var button = document.getElementById("btn_inspect");
    indicator.style.display = isLoading ? 'flex' : 'none';
    if (text && loadingText) loadingText.textContent = text;
    button.disabled = isLoading;
}

function getScale() {
    var img = document.getElementById("screenshot");
    if (!img || !img.naturalWidth || !img.naturalHeight) return { scaleX: 1, scaleY: 1 };
    return {
        scaleX: (img.clientWidth / img.naturalWidth) || 1,
        scaleY: (img.clientHeight / img.naturalHeight) || 1,
    };
}

// ─────────────────────────────────────────────
// Inspector type toggle
// ─────────────────────────────────────────────

function toggleInspector() {
    var type = document.getElementById("inspectorType").value;
    state.inspectorType = type;
    document.getElementById("opencvControls").style.display = type === "opencv" ? "block" : "none";
    document.getElementById("lvglControls").style.display = type === "lvgl" ? "block" : "none";
    document.getElementById("btn_inspect").disabled = false;
}

function onCaptureMethodChange() {
    var method = document.getElementById("lvglCaptureMethod").value;
    document.getElementById("qemuMonitorSettings").style.display =
        method === "qemu_monitor" ? "block" : "none";
    document.getElementById("vncSettings").style.display =
        method === "vnc" ? "block" : "none";
}

// ─────────────────────────────────────────────
// Entry point
// ─────────────────────────────────────────────

function inspect() {
    if (state.inspectorType === "opencv") {
        inspectOpenCV();
    } else {
        inspectLVGL();
    }
}

// ─────────────────────────────────────────────
// OpenCV / pywinauto desktop inspector
// ─────────────────────────────────────────────

function inspectOpenCV() {
    var selectedValue = document.getElementById("exampleDataList").value.trim();
    if (!selectedValue) {
        setStatus("Select a window before inspecting.", "warn");
        return;
    }
    setLoading(true, "Detecting UI elements with OpenCV…");
    setStatus("Inspecting window…", "info");
    var startTime = performance.now();

    fetch(`/inspect/${encodeURIComponent(selectedValue)}`)
        .then(function(response) {
            if (!response.ok) {
                return response.json().then(function(d) { throw new Error(d.error || "HTTP " + response.status); });
            }
            return response.json();
        })
        .then(function(data) {
            if (data.error) throw new Error(data.error);

            state.tree = data.tree;
            state.windowRect = data.window_rect || null;
            try { localStorage.setItem('inspect', JSON.stringify(data.tree)); } catch(_) {}

            showContainer();
            displayTree(data.tree);
            setScreenshot("data:image/png;base64," + data.printscreen);
            setStatus("Ready · " + formatTime(performance.now() - startTime), "ok");
        })
        .catch(function(e) {
            setStatus(e.message || "Inspection failed", "error");
        })
        .finally(function() {
            setLoading(false);
        });
}

// ─────────────────────────────────────────────
// LVGL Inspector — screenshot and tree are INDEPENDENT
// ─────────────────────────────────────────────

function inspectLVGL() {
    setLoading(true, "Connecting to LVGL device…");
    setStatus("Inspecting LVGL application…", "info");

    var startTime = performance.now();
    var captureMethod = document.getElementById("lvglCaptureMethod").value;
    var lvglIp    = (document.getElementById("lvglIp").value || "192.168.0.10").trim();
    var lvglPort  = parseInt(document.getElementById("lvglPort").value, 10) || 8080;
    var vncHost   = (document.getElementById("vncHost")  || {value: "192.168.0.10"}).value;
    var vncPort   = parseInt((document.getElementById("vncPort") || {value:"5900"}).value, 10) || 5900;
    var monHost   = (document.getElementById("qemuMonitorHost") || {value: "127.0.0.1"}).value;
    var monPort   = parseInt((document.getElementById("qemuMonitorPort") || {value:"55555"}).value, 10) || 55555;
    var qmpSocket = (document.getElementById("qemuQmpSocket") || {value: "/tmp/qemu.sock"}).value;

    // ── Always show the workspace container immediately ──────────────
    showContainer();

    var pendingCount = 0;
    var anySuccess   = false;

    function taskStart() { pendingCount++; }
    function taskDone(ok) {
        if (ok) anySuccess = true;
        pendingCount--;
        if (pendingCount <= 0) {
            setLoading(false);
            setStatus(
                anySuccess
                    ? "Ready · " + formatTime(performance.now() - startTime)
                    : "Completed with errors",
                anySuccess ? "ok" : "warn"
            );
        }
    }

    // ── Task 1: Screenshot ───────────────────────────────────────────
    if (captureMethod !== "none") {
        taskStart();
        setLoadingText("Capturing QEMU screenshot…");

        var screenshotBody = {
            capture:             captureMethod,
            vnc_host:            vncHost,
            vnc_port:            vncPort,
            qemu_monitor_host:   monHost,
            qemu_monitor_port:   monPort,
            qemu_qmp_socket:     qmpSocket,
            qemu_window_titles:  ["qemu-system", "qemu", "qemu-system-aarch64", "qemu-system-x86_64"],
        };

        fetch('/lvgl/screenshot', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(screenshotBody),
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.error) {
                setStatus("Screenshot warning: " + data.error, "warn");
                taskDone(false);
                return;
            }
            if (data.screenshot) {
                setScreenshot("data:image/png;base64," + data.screenshot);
                if (data.fallback) {
                    setStatus("Screenshot via fallback (" + data.fallback + ")", "warn");
                }
                taskDone(true);
            } else {
                setStatus("Screenshot returned empty", "warn");
                taskDone(false);
            }
        })
        .catch(function(e) {
            setStatus("Screenshot failed: " + (e.message || e), "warn");
            taskDone(false);
        });
    }

    // ── Task 2: LVGL UI Tree ─────────────────────────────────────────
    taskStart();
    setLoadingText("Loading UI tree…");

    fetch('/lvgl/inspect', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            element:          "root",
            max_depth:        null,
            ip:               lvglIp,
            port:             lvglPort,
            capture:          "none",   // screenshot already handled above
            scan_extra_roots: true,
            deep_scan:        true,
            scan_hidden:      true,
        }),
    })
    .then(function(r) {
        if (!r.ok) {
            return r.json().then(function(d) { throw new Error(d.error || "HTTP " + r.status); });
        }
        return r.json();
    })
    .then(function(data) {
        if (data.error) throw new Error(data.error);
        state.tree = data.tree;
        try { localStorage.setItem('inspect', JSON.stringify(data.tree)); } catch(_) {}
        displayTree(data.tree);
        taskDone(true);
    })
    .catch(function(e) {
        var msg = e.message || String(e);
        document.getElementById("tree-menu").innerHTML =
            '<p class="empty error-text">Tree error: ' + escapeHtml(msg) + '</p>';
        setStatus("Tree error: " + msg, "error");
        taskDone(false);
    });
}

// ─────────────────────────────────────────────
// DOM helpers
// ─────────────────────────────────────────────

function showContainer() {
    document.getElementById("container").style.display = "grid";
}

function setLoadingText(text) {
    var el = document.getElementById("loadingText");
    if (el) el.textContent = text;
}

function setScreenshot(src) {
    var img = document.getElementById("screenshot");
    var placeholder = document.getElementById("screenshotPlaceholder");
    img.onload = function() {
        img.style.display = "block";
        if (placeholder) placeholder.style.display = "none";
    };
    img.onerror = function() {
        img.style.display = "none";
        if (placeholder) { placeholder.style.display = "flex"; placeholder.querySelector("span").textContent = "Failed to decode screenshot"; }
    };
    img.src = src;
}

function escapeHtml(s) {
    return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

// ─────────────────────────────────────────────
// Tree rendering
// ─────────────────────────────────────────────

function displayTree(tree) {
    var treeMenu = document.getElementById('tree-menu');
    treeMenu.innerHTML = '';
    state.nodeDictionary = {};
    loadExpandedState();

    if (!tree || !tree.attributes) {
        treeMenu.innerHTML = '<p class="empty">No UI tree data available.</p>';
        return;
    }

    var treeList = document.createElement('ul');
    treeList.className = "tree-list";
    createTreeMenu(tree, treeList, 0);
    treeMenu.appendChild(treeList);
}

function createTreeMenu(node, parentElement, depth) {
    var listItem = document.createElement('li');
    listItem.className = "tree-item";
    listItem.dataset.nodeId = node.idx;

    var expanded = depth === 0;
    if (Object.prototype.hasOwnProperty.call(state.treeExpandedState, String(node.idx))) {
        expanded = !!state.treeExpandedState[String(node.idx)];
    }
    listItem.dataset.expanded = expanded ? "true" : "false";

    var row = document.createElement('div');
    row.className = "tree-row";

    var hasChildren = node.children && node.children.length > 0;

    var toggle = document.createElement('button');
    toggle.type = "button";
    toggle.className = "tree-toggle" + (hasChildren ? "" : " empty");
    toggle.textContent = hasChildren ? (expanded ? "▾" : "▸") : "";
    toggle.disabled = !hasChildren;

    var button = document.createElement('button');
    button.type = "button";
    button.className = "tree-button";
    button.textContent = node.attributes.title || node.attributes.control_type || 'Unnamed Node';

    var meta = document.createElement('span');
    meta.className = "tree-meta";
    meta.textContent = node.attributes.control_type || "Unknown";

    button.addEventListener('click', function() { setActiveNode(node.idx); });
    toggle.addEventListener('click', function() {
        if (!toggle.disabled) toggleVisibility(listItem, toggle);
    });

    row.appendChild(toggle);
    row.appendChild(button);
    row.appendChild(meta);
    listItem.appendChild(row);
    parentElement.appendChild(listItem);
    state.nodeDictionary[node.idx] = listItem;

    if (hasChildren) {
        var sublist = document.createElement('ul');
        sublist.className = "tree-children";
        sublist.style.display = expanded ? "block" : "none";
        node.children.forEach(function(child) { createTreeMenu(child, sublist, depth + 1); });
        listItem.appendChild(sublist);
    }
}

function setNodeExpanded(element, expand) {
    var sublist = element.querySelector('.tree-children');
    if (!sublist) return;
    sublist.style.display = expand ? 'block' : 'none';
    element.dataset.expanded = expand ? "true" : "false";
    var toggle = element.querySelector('.tree-toggle');
    if (toggle && !toggle.disabled) toggle.textContent = expand ? "▾" : "▸";
    state.treeExpandedState[String(element.dataset.nodeId)] = !!expand;
    saveExpandedState();
}

function toggleVisibility(element, toggleControl) {
    var sublist = element.querySelector('.tree-children');
    if (sublist) {
        var isCollapsed = sublist.style.display === 'none';
        setNodeExpanded(element, isCollapsed);
        if (toggleControl) toggleControl.textContent = isCollapsed ? "▾" : "▸";
    }
}

function expandAllTree() {
    document.querySelectorAll('.tree-item').forEach(function(n) { setNodeExpanded(n, true); });
}

function collapseAllTree() {
    document.querySelectorAll('.tree-item').forEach(function(n, i) { setNodeExpanded(n, i === 0); });
}

// ─────────────────────────────────────────────
// Node selection & highlight
// ─────────────────────────────────────────────

function setActiveNode(nodeId) {
    if (state.activeNodeId !== null) {
        var prev = state.nodeDictionary[state.activeNodeId];
        if (prev) prev.classList.remove('selected');
    }
    var selected = state.nodeDictionary[nodeId];
    if (selected) {
        selected.classList.add('selected');
        selected.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    state.activeNodeId = nodeId;
    var node = getNodeByIdx(nodeId);
    if (node) {
        highlightNode(node);
        updateAttributes(node);
    }
}

function findNodeByIdx(node, targetIdx) {
    if (node.idx === targetIdx) return node;
    for (var i = 0; i < (node.children || []).length; i++) {
        var r = findNodeByIdx(node.children[i], targetIdx);
        if (r) return r;
    }
    return null;
}

function getNodeByIdx(idx) {
    try {
        var data = JSON.parse(localStorage.getItem('inspect') || 'null');
        return data ? findNodeByIdx(data, parseInt(idx, 10)) : null;
    } catch(_) { return null; }
}

function updateAttributes(node) {
    document.getElementById('form_title').value       = node.attributes.title        || "";
    document.getElementById('form_auto_id').value     = node.attributes.auto_id      || "";
    document.getElementById('form_control_type').value= node.attributes.control_type || "";
    document.getElementById('form_path').value        = JSON.stringify(node.attributes);

    // Show selector / locator info if available
    var locators = node.attributes.locators || {};
    var locatorEl = document.getElementById('form_locator');
    if (locatorEl) {
        var lines = Object.entries(locators).map(function(kv) { return kv[0] + ":\n  " + kv[1]; });
        locatorEl.value = lines.join("\n\n") || (node.attributes.selector_usage || []).join("\n") || "";
    }
}

function highlightNode(node) {
    if (!node || !node.rect) return;

    var highlightEl = document.getElementById('highlightDiv');
    if (!highlightEl) {
        highlightEl = document.createElement('div');
        highlightEl.id = 'highlightDiv';
        document.getElementById('img_content').appendChild(highlightEl);
    }

    var img       = document.getElementById("screenshot");
    var canvas    = document.getElementById('img_content');
    var canvasRect = canvas.getBoundingClientRect();
    var imgRect   = img.getBoundingClientRect();
    var scale     = getScale();
    state.scaleX  = scale.scaleX;
    state.scaleY  = scale.scaleY;

    var offsetX  = imgRect.left - canvasRect.left;
    var offsetY  = imgRect.top  - canvasRect.top;
    var rectLeft = node.rect.Left;
    var rectTop  = node.rect.Top;

    if (state.windowRect) {
        rectLeft -= state.windowRect.left;
        rectTop  -= state.windowRect.top;
    }

    highlightEl.style.left    = (offsetX + rectLeft * state.scaleX) + "px";
    highlightEl.style.top     = (offsetY + rectTop  * state.scaleY) + "px";
    highlightEl.style.width   = ((node.rect.Right  - node.rect.Left) * state.scaleX) + "px";
    highlightEl.style.height  = ((node.rect.Bottom - node.rect.Top)  * state.scaleY) + "px";
    highlightEl.style.display = "block";
}

function clearHighlight() {
    var el = document.getElementById('highlightDiv');
    if (el) el.style.display = "none";
}

// ─────────────────────────────────────────────
// Copy selector
// ─────────────────────────────────────────────

function copyPath() {
    var val = document.getElementById("form_path").value;
    if (!val) { setStatus("No node selected.", "warn"); return; }
    navigator.clipboard.writeText(val).then(function() {
        setStatus("Copied to clipboard.", "ok");
    }).catch(function() {
        var ta = document.createElement("textarea");
        ta.value = val;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        setStatus("Copied to clipboard.", "ok");
    });
}

// ─────────────────────────────────────────────
// Mouse interactions
// ─────────────────────────────────────────────

document.addEventListener('mouseover', function(event) {
    if (event.target.classList.contains('tree-button')) {
        var nodeId = event.target.closest('.tree-item').dataset.nodeId;
        var node = getNodeByIdx(nodeId);
        if (node) highlightNode(node);
    }
});

document.addEventListener('mouseout', function(event) {
    if (event.target.classList.contains('tree-button')) {
        if (state.activeNodeId === null) clearHighlight();
    }
});

// Ctrl+mousemove over screenshot → snap to nearest node
(function() {
    var imgContent = document.getElementById('img_content');
    if (!imgContent) return;
    imgContent.addEventListener('mousemove', function(event) {
        if (!state.tree || !event.ctrlKey) return;
        var img = document.getElementById("screenshot");
        if (!img) return;
        var rect  = img.getBoundingClientRect();
        var scale = getScale();
        var origX = (event.clientX - rect.left) / scale.scaleX;
        var origY = (event.clientY - rect.top)  / scale.scaleY;
        if (state.windowRect) { origX += state.windowRect.left; origY += state.windowRect.top; }
        var node = findClosestNode(state.tree, origX, origY);
        if (node) setActiveNode(node.idx);
    });
})();

function findClosestNode(root, x, y) {
    var best = null, bestDist = Infinity;
    function walk(n) {
        var d = Math.hypot(x - n.center.X, y - n.center.Y);
        if (d < bestDist) { bestDist = d; best = n; }
        (n.children || []).forEach(walk);
    }
    walk(root);
    return best;
}

// ─────────────────────────────────────────────
// Init
// ─────────────────────────────────────────────

window.onload = function() {
    document.getElementById("container").style.display = "none";
    setStatus("Ready", "ok");
    document.getElementById("opencvControls").style.display = "block";
    document.getElementById("lvglControls").style.display = "none";
    document.getElementById("btn_inspect").disabled = false;
    // init capture-method visibility
    if (document.getElementById("lvglCaptureMethod")) onCaptureMethodChange();
};