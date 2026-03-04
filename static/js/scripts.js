const state = {
    tree: null,
    nodeDictionary: {},
    activeNodeId: null,
    scaleX: 1,
    scaleY: 1,
    windowRect: null,
    currentMode: "windows", // Track the current UI mode
};

function formatTime(milliseconds) {
    var seconds = Math.floor(milliseconds / 1000);
    var hours = Math.floor(seconds / 3600);
    var minutes = Math.floor((seconds % 3600) / 60);
    var remainingSeconds = seconds % 60;
    return `${pad(hours)}:${pad(minutes)}:${pad(remainingSeconds)}`;
}

function pad(value) {
    return value < 10 ? '0' + value : value;
}

function setStatus(text, type) {
    var status = document.getElementById("status");
    status.textContent = text;
    status.dataset.type = type || "info";
}

function setLoading(isLoading) {
    var loadingIndicator = document.getElementById("loadingIndicator");
    var button = document.getElementById("btn_inspect");
    loadingIndicator.style.display = isLoading ? 'block' : 'none';
    if (!button) {
        return;
    }
    if (isLoading) {
        button.disabled = true;
        return;
    }
    updateInspectButtonState();
}

function updateInspectButtonState() {
    var button = document.getElementById("btn_inspect");
    if (!button) {
        return;
    }
    if (state.currentMode === "lvgl") {
        button.disabled = false;
        return;
    }
    var input = document.getElementById("exampleDataList");
    var selectedValue = input ? input.value.trim() : "";
    button.disabled = !selectedValue;
}

function getScale() {
    var imgElement = document.getElementById("screenshot");
    if (!imgElement || !imgElement.naturalWidth || !imgElement.naturalHeight) {
        return { scaleX: 1, scaleY: 1 };
    }
    var scaleX = imgElement.clientWidth / imgElement.naturalWidth;
    var scaleY = imgElement.clientHeight / imgElement.naturalHeight;
    return { scaleX: scaleX || 1, scaleY: scaleY || 1 };
}

function applyScreenshotResponse(data) {
    var imgElement = document.getElementById("screenshot");
    var placeholder = document.getElementById("screenshotPlaceholder");
    if (!imgElement) {
        return;
    }
    if (data.image_url) {
        imgElement.src = data.image_url;
    } else if (data.screenshot) {
        imgElement.src = `data:image/png;base64, ${data.screenshot}`;
    } else if (data.printscreen) {
        imgElement.src = `data:image/png;base64, ${data.printscreen}`;
    } else {
        return;
    }
    imgElement.style.display = "block";
    if (placeholder) {
        placeholder.style.display = "none";
    }
}

function getLvglRequestPayload() {
    var captureEl = document.getElementById("lvglCaptureMethod");
    var lvglIpEl = document.getElementById("lvglIp");
    var lvglPortEl = document.getElementById("lvglPort");
    var vncHostEl = document.getElementById("vncHost");
    var vncPortEl = document.getElementById("vncPort");
    var monitorHostEl = document.getElementById("qemuMonitorHost");
    var monitorPortEl = document.getElementById("qemuMonitorPort");
    var qmpSocketEl = document.getElementById("qemuQmpSocket");

    return {
        capture: captureEl ? captureEl.value : "qemu_monitor",
        ip: lvglIpEl ? lvglIpEl.value : "192.168.0.10",
        port: lvglPortEl ? parseInt(lvglPortEl.value || "8080", 10) : 8080,
        vnc_host: vncHostEl ? vncHostEl.value : "192.168.0.10",
        vnc_port: vncPortEl ? parseInt(vncPortEl.value || "5900", 10) : 5900,
        qemu_monitor_host: monitorHostEl ? monitorHostEl.value : "127.0.0.1",
        qemu_monitor_port: monitorPortEl ? parseInt(monitorPortEl.value || "55555", 10) : 55555,
        qemu_qmp_socket: qmpSocketEl ? qmpSocketEl.value : "/tmp/qemu.sock"
    };
}

function onCaptureMethodChange() {
    var methodEl = document.getElementById("lvglCaptureMethod");
    var qemuSettings = document.getElementById("qemuMonitorSettings");
    var vncSettings = document.getElementById("vncSettings");
    var method = methodEl ? methodEl.value : "qemu_monitor";

    if (qemuSettings) {
        qemuSettings.style.display = method === "qemu_monitor" ? "block" : "none";
    }
    if (vncSettings) {
        vncSettings.style.display = method === "vnc" ? "block" : "none";
    }
}

function inspect() {
    // Check current mode to determine which inspection to perform
    if (state.currentMode === "lvgl") {
        inspectLvgl();
        return;
    }

    var selectedValue = document.getElementById("exampleDataList").value.trim();
    if (!selectedValue) {
        setStatus("Select a window before inspecting.", "warn");
        return;
    }
    setLoading(true);
    setStatus("Inspecting window…", "info");
    var startTime = performance.now();
    var success = false;

    fetch(`/inspect/${encodeURIComponent(selectedValue)}`)
        .then(response => {
            if (!response.ok) {
                return response.json().then(data => {
                    throw new Error(data.error || "Inspect failed");
                });
            }
            return response.json();
        })
        .then(data => {
            state.tree = data.tree;
            state.windowRect = data.window_rect || null;
            localStorage.setItem('inspect', JSON.stringify(data.tree));
            displayTree(data.tree);
            applyScreenshotResponse(data);
            var container = document.getElementById('container');
            container.style.display = 'grid';
            success = true;
        })
        .catch(error => {
            console.error('Error:', error);
            setStatus(error.message || "Inspect failed", "error");
        }).finally(() => {
            setLoading(false);
            var endTime = performance.now();
            var elapsedTime = endTime - startTime;
            var formattedElapsedTime = formatTime(elapsedTime);
            if (success) {
                setStatus(`Ready · ${formattedElapsedTime}`, "ok");
            }
        });
}

function displayTree(tree) {
    var treeMenu = document.getElementById('tree-menu');
    treeMenu.innerHTML = '';
    state.nodeDictionary = {};
    if (!tree || !tree.attributes) {
        treeMenu.innerHTML = '<p class="empty">No UI tree data available.</p>';
        return;
    }
    var treeList = document.createElement('ul');
    treeList.className = "tree-list";
    createTreeMenu(tree, treeList);
    treeMenu.appendChild(treeList);
}

function createTreeMenu(node, parentElement) {
    var listItem = document.createElement('li');
    listItem.className = "tree-item";
    listItem.dataset.nodeId = node.idx;

    var button = document.createElement('button');
    button.type = "button";
    button.className = "tree-button";
    button.textContent = node.attributes.title || node.attributes.control_type || 'Unnamed Node';

    var meta = document.createElement('span');
    meta.className = "tree-meta";
    meta.textContent = node.attributes.control_type || "Unknown";

    button.addEventListener('click', function () {
        setActiveNode(node.idx);
        toggleVisibility(listItem);
    });

    listItem.appendChild(button);
    listItem.appendChild(meta);
    parentElement.appendChild(listItem);
    state.nodeDictionary[node.idx] = listItem;

    if (node.children && node.children.length > 0) {
        var sublist = document.createElement('ul');
        sublist.className = "tree-children";
        node.children.forEach(child => createTreeMenu(child, sublist));
        listItem.appendChild(sublist);
    }
}

function toggleVisibility(element) {
    var sublist = element.querySelector('.tree-children');
    if (sublist) {
        var isCollapsed = sublist.style.display === 'none';
        sublist.style.display = isCollapsed ? 'block' : 'none';
    }
}

function setActiveNode(nodeId) {
    if (state.activeNodeId !== null) {
        var previous = state.nodeDictionary[state.activeNodeId];
        if (previous) {
            previous.classList.remove('selected');
        }
    }
    var selected = state.nodeDictionary[nodeId];
    if (selected) {
        selected.classList.add('selected');
    }
    state.activeNodeId = nodeId;
    var node = getNodeByIdxFromLocalStorage(nodeId);
    if (node) {
        highlightDiv(node);
        updateAttributes(node);
    }
}

function findNodeByIdx(node, targetIdx) {
    if (node.idx === targetIdx) {
        return node;
    }
    for (const child of node.children || []) {
        const result = findNodeByIdx(child, targetIdx);
        if (result) {
            return result;
        }
    }
    return null;
}

function getNodeByIdxFromLocalStorage(idx) {
    const storedData = localStorage.getItem('inspect');
    const data = storedData ? JSON.parse(storedData) : null;
    if (data) {
        return findNodeByIdx(data, parseInt(idx));
    }
    return null;
}

function updateAttributes(node) {
    document.getElementById('form_title').value = node.attributes.title || "";
    document.getElementById('form_auto_id').value = node.attributes.auto_id || "";
    document.getElementById('form_control_type').value = node.attributes.control_type || "";
    document.getElementById('form_path').value = JSON.stringify(node.attributes);
}

function highlightDiv(node) {
    if (!node || !node.rect) {
        return;
    }
    var highlightEl = document.getElementById('highlightDiv');
    if (!highlightEl) {
        highlightEl = document.createElement('div');
        highlightEl.id = 'highlightDiv';
        document.getElementById('img_content').appendChild(highlightEl);
    }

    var imgElement = document.getElementById("screenshot");
    var canvas = document.getElementById('img_content');
    var canvasRect = canvas.getBoundingClientRect();
    var imgRect = imgElement.getBoundingClientRect();
    var scale = getScale();
    state.scaleX = scale.scaleX;
    state.scaleY = scale.scaleY;

    var offsetX = imgRect.left - canvasRect.left;
    var offsetY = imgRect.top - canvasRect.top;
    var rectLeft = node.rect.Left;
    var rectTop = node.rect.Top;
    if (state.windowRect) {
        rectLeft = rectLeft - state.windowRect.left;
        rectTop = rectTop - state.windowRect.top;
    }
    var left = offsetX + (rectLeft * state.scaleX);
    var top = offsetY + (rectTop * state.scaleY);
    var width = (node.rect.Right - node.rect.Left) * state.scaleX;
    var height = (node.rect.Bottom - node.rect.Top) * state.scaleY;

    highlightEl.style.left = `${left}px`;
    highlightEl.style.top = `${top}px`;
    highlightEl.style.width = `${width}px`;
    highlightEl.style.height = `${height}px`;
    highlightEl.style.opacity = "1";
    highlightEl.style.display = "block";
}

function clearHighlight() {
    var highlightEl = document.getElementById('highlightDiv');
    if (highlightEl) {
        highlightEl.style.display = "none";
    }
}

window.onload = function () {
    var container = document.getElementById('container');
    container.style.display = 'none';
    setStatus("Ready", "ok");
    
    // Initialize UI mode
    switchUiMode();
    updateInspectButtonState();

    var windowInput = document.getElementById("exampleDataList");
    if (windowInput) {
        windowInput.addEventListener("input", updateInspectButtonState);
        windowInput.addEventListener("change", updateInspectButtonState);
    }
    onCaptureMethodChange();
};

function releaseInspectButton() {
    updateInspectButtonState();
}

function copyPath() {
    var selectedValue = document.getElementById("form_path").value;
    if (!selectedValue) {
        setStatus("No node selected to copy.", "warn");
        return;
    }
    navigator.clipboard.writeText(selectedValue).then(function () {
        setStatus("Path copied to clipboard.", "ok");
    }).catch(function () {
        var textarea = document.createElement("textarea");
        textarea.value = selectedValue;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        setStatus("Path copied to clipboard.", "ok");
    });
}

document.addEventListener('mouseover', function (event) {
    if (event.target.classList.contains('tree-button')) {
        var nodeId = event.target.parentElement.dataset.nodeId;
        var node = getNodeByIdxFromLocalStorage(nodeId);
        highlightDiv(node);
    }
});

document.addEventListener('mouseout', function (event) {
    if (event.target.classList.contains('tree-button')) {
        clearHighlight();
    }
});

var imgContent = document.getElementById('img_content');
if (imgContent) {
    imgContent.addEventListener('mousemove', function (event) {
        if (!state.tree) {
            return;
        }
        if (!event.ctrlKey) {
            return;
        }
        var imgElement = document.getElementById("screenshot");
        if (!imgElement) {
            return;
        }
        var rect = imgElement.getBoundingClientRect();
        var mouseXRelative = event.clientX - rect.left;
        var mouseYRelative = event.clientY - rect.top;
        var scale = getScale();
        var originalX = mouseXRelative / scale.scaleX;
        var originalY = mouseYRelative / scale.scaleY;
        if (state.windowRect) {
            originalX += state.windowRect.left;
            originalY += state.windowRect.top;
        }
        var node = findNodeByCoordinates(state.tree, originalX, originalY);
        if (node) {
            setActiveNode(node.idx);
        }
    });
}

function findNodeByCoordinates(node, targetX, targetY) {
    let closestNode = null;
    let minDistance = Number.MAX_SAFE_INTEGER;

    function findClosestNode(currentNode, x, y) {
        const distance = Math.sqrt(Math.pow(x - currentNode.center.X, 2) + Math.pow(y - currentNode.center.Y, 2));
        if (distance < minDistance) {
            minDistance = distance;
            closestNode = currentNode;
        }

        for (const child of currentNode.children || []) {
            findClosestNode(child, x, y);
        }
    }

    findClosestNode(node, targetX, targetY);
    return closestNode;
}

function switchUiMode() {
    const modeSelect = document.getElementById("inspectorType");
    const mode = modeSelect ? modeSelect.value : "opencv";
    const windowsControls = document.getElementById("opencvControls");
    const lvglControls = document.getElementById("lvglControls");
    const inspectBtn = document.getElementById("btn_inspect");
    const lvglInspectBtn = document.getElementById("btn_lvgl_inspect");

    if (!windowsControls || !lvglControls || !inspectBtn) {
        return;
    }

    if (mode === "lvgl") {
        // Switch to LVGL mode
        windowsControls.style.display = "none";
        lvglControls.style.display = "block";
        inspectBtn.style.display = "inline-block";
        if (lvglInspectBtn) {
            lvglInspectBtn.style.display = "none";
        }
        state.currentMode = "lvgl";
        setStatus("LVGL/QEMU mode active", "info");
    } else {
        // Switch back to Windows mode
        windowsControls.style.display = "block";
        lvglControls.style.display = "none";
        inspectBtn.style.display = "inline-block";
        if (lvglInspectBtn) {
            lvglInspectBtn.style.display = "none";
        }
        state.currentMode = "windows";
        setStatus("Windows UI mode active", "info");
    }
    updateInspectButtonState();
}

function toggleInspector() {
    switchUiMode();
}

function captureLvglScreenshot() {
    setLoading(true);
    setStatus("Capturing QEMU screenshot…", "info");
    var startTime = performance.now();

    var payload = getLvglRequestPayload();
    fetch('/lvgl/screenshot', {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    })
        .then(response => {
            if (!response.ok) {
                return response.json().then(data => {
                    throw new Error(data.error || "QEMU screenshot failed");
                });
            }
            return response.json();
        })
        .then(data => {
            applyScreenshotResponse(data);
            var container = document.getElementById('container');
            container.style.display = 'grid';
            setStatus("QEMU screenshot captured successfully", "ok");
        })
        .catch(error => {
            console.error('Error:', error);
            setStatus(error.message || "QEMU screenshot error", "error");
        }).finally(() => {
            setLoading(false);
            var endTime = performance.now();
            var elapsedTime = endTime - startTime;
            var formattedElapsedTime = formatTime(elapsedTime);
            setStatus(`Ready · ${formattedElapsedTime}`, "ok");
        });
}

function findLvglVisual() {
    if (state.currentMode !== "lvgl") {
        setStatus("Switch to LVGL mode to use visual matching.", "warn");
        return;
    }

    var templatePathEl = document.getElementById("lvglTemplatePath");
    var thresholdEl = document.getElementById("lvglMatchThreshold");
    var templatePath = templatePathEl ? templatePathEl.value.trim() : "";
    var threshold = thresholdEl ? parseFloat(thresholdEl.value || "0.8") : 0.8;

    if (!templatePath) {
        setStatus("Enter a template path first.", "warn");
        return;
    }
    if (isNaN(threshold) || threshold < 0 || threshold > 1) {
        setStatus("Match threshold must be between 0 and 1.", "warn");
        return;
    }

    setLoading(true);
    setStatus("Running visual match...", "info");
    var payload = getLvglRequestPayload();
    payload.template_path = templatePath;
    payload.threshold = threshold;

    fetch('/lvgl/find-visual', {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    })
        .then(response => response.json().then(data => ({ ok: response.ok, data: data })))
        .then(result => {
            if (!result.ok) {
                throw new Error(result.data.error || "Visual match failed");
            }
            var data = result.data;
            if (!data.matched) {
                setStatus(`No match above threshold (${data.confidence.toFixed(3)}).`, "warn");
                return;
            }
            var matchNode = {
                rect: data.rect,
                center: data.center,
                attributes: {
                    title: "Visual Match",
                    auto_id: "",
                    control_type: "Template",
                    confidence: data.confidence,
                    template_path: templatePath
                }
            };
            highlightDiv(matchNode);
            updateAttributes(matchNode);
            setStatus(`Visual match found (${data.confidence.toFixed(3)}).`, "ok");
        })
        .catch(error => {
            console.error('Error:', error);
            setStatus(error.message || "Visual match failed", "error");
        })
        .finally(() => {
            setLoading(false);
        });
}

function inspectLvgl() {
    setLoading(true);
    setStatus("Inspecting LVGL application...", "info");
    var startTime = performance.now();
    var success = false;
    var payload = getLvglRequestPayload();

    Promise.allSettled([
        fetch('/lvgl/inspect', {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        }).then(response => {
            if (!response.ok) {
                return response.json().then(data => {
                    throw new Error(data.error || "LVGL inspection failed");
                });
            }
            return response.json();
        }),
        fetch('/lvgl/screenshot', {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        }).then(response => {
            if (!response.ok) {
                return response.json().then(data => {
                    throw new Error(data.error || "LVGL screenshot failed");
                });
            }
            return response.json();
        })
    ])
        .then(results => {
            var inspectResult = results[0];
            var screenshotResult = results[1];
            var inspectError = null;
            var screenshotError = null;

            if (inspectResult.status === "fulfilled") {
                var inspectData = inspectResult.value;
                state.tree = inspectData.tree;
                state.windowRect = inspectData.window_rect || null;
                localStorage.setItem('inspect', JSON.stringify(inspectData.tree));
                displayTree(inspectData.tree);
                success = true;
            } else {
                inspectError = inspectResult.reason;
            }

            if (screenshotResult.status === "fulfilled") {
                applyScreenshotResponse(screenshotResult.value);
                success = true;
            } else {
                screenshotError = screenshotResult.reason;
            }

            if (success) {
                var container = document.getElementById('container');
                container.style.display = 'grid';
                if (inspectError || screenshotError) {
                    var partialError = inspectError || screenshotError;
                    setStatus(`Partial success: ${partialError.message || partialError}`, "warn");
                }
                return;
            }

            var combined = `${inspectError ? (inspectError.message || inspectError) : ""} ${screenshotError ? (screenshotError.message || screenshotError) : ""}`.trim();
            throw new Error(combined || "LVGL inspection failed");
        })
        .catch(error => {
            console.error('Error:', error);
            setStatus(error.message || "LVGL inspection failed", "error");
        }).finally(() => {
            setLoading(false);
            var endTime = performance.now();
            var elapsedTime = endTime - startTime;
            var formattedElapsedTime = formatTime(elapsedTime);
            if (success) {
                setStatus(`LVGL inspection completed · ${formattedElapsedTime}`, "ok");
            }
        });
}
