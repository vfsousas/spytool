const state = {
    tree: null,
    nodeDictionary: {},
    activeNodeId: null,
    scaleX: 1,
    scaleY: 1,
    windowRect: null,
    inspectorType: "opencv", // Changed default to opencv
    treeExpandedState: {},
};

const TREE_EXPANDED_KEY = "tree_expanded_state";

function loadExpandedState() {
    try {
        var raw = localStorage.getItem(TREE_EXPANDED_KEY);
        state.treeExpandedState = raw ? JSON.parse(raw) : {};
    } catch (error) {
        state.treeExpandedState = {};
    }
}

function saveExpandedState() {
    localStorage.setItem(TREE_EXPANDED_KEY, JSON.stringify(state.treeExpandedState));
}

function formatTime(milliseconds) {
    var seconds = Math.floor(milliseconds / 1000);
    var hours = Math.floor((seconds / 3600));
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
    button.disabled = isLoading;
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

function toggleInspector() {
    var inspectorType = document.getElementById("inspectorType").value;
    state.inspectorType = inspectorType;
    
    if (inspectorType === "opencv") {
        document.getElementById("opencvControls").style.display = "block";
        document.getElementById("lvglControls").style.display = "none";
    } else {
        document.getElementById("opencvControls").style.display = "none";
        document.getElementById("lvglControls").style.display = "block";
    }
    document.getElementById("btn_inspect").disabled = false;
}

function inspect() {
    if (state.inspectorType === "opencv") {
        inspectOpenCV();
    } else {
        inspectLVGL();
    }
}

function inspectOpenCV() {
    var selectedValue = document.getElementById("exampleDataList").value.trim();
    if (!selectedValue) {
        setStatus("Select a window before inspecting.", "warn");
        document.getElementById("btn_inspect").disabled = false; // Re-enable button if no window selected
        return;
    }
    setLoading(true);
    setStatus("Inspecting window with OpenCV…", "info");
    var startTime = performance.now();
    var success = false;

    fetch(`/inspect/${encodeURIComponent(selectedValue)}`)
        .then(response => {
            if (!response.ok) {
                // Handle non-200 responses
                return response.json().then(data => {
                    throw new Error(data.error || `HTTP error! status: ${response.status}`);
                });
            }
            return response.json();
        })
        .then(data => {
            // Check if the response contains an error
            if (data.error) {
                throw new Error(data.error);
            }
            
            state.tree = data.tree;
            state.windowRect = data.window_rect || null;
            localStorage.setItem('inspect', JSON.stringify(data.tree));
            displayTree(data.tree);
            var imgElement = document.getElementById("screenshot");
            imgElement.src = `data:image/png;base64, ${data.printscreen}`;
            var container = document.getElementById('container');
            container.style.display = 'grid';
            success = true;
        })
        .catch(error => {
            console.error('Error:', error);
            setStatus(error.message || "Unexpected error during inspection", "error");
        }).finally(() => {
            setLoading(false);
            var endTime = performance.now();
            var elapsedTime = endTime - startTime;
            var formattedElapsedTime = formatTime(elapsedTime);
            if (success) {
                setStatus(`Ready · ${formattedElapsedTime}`, "ok");
            }
            // Always ensure the button is enabled after the operation completes
            document.getElementById("btn_inspect").disabled = false;
        });
}

function inspectLVGL() {
    setLoading(true);
    setStatus("Inspecting LVGL application via Client(ip, port)…", "info");
    var startTime = performance.now();
    var success = false;
    
    // Get capture method and settings
    var captureMethod = document.getElementById("lvglCaptureMethod").value;
    var vncHost = document.getElementById("vncHost").value;
    var vncPort = document.getElementById("vncPort").value;
    var lvglIp = document.getElementById("lvglIp").value.trim() || "127.0.0.1";
    var lvglPort = parseInt(document.getElementById("lvglPort").value, 10) || 8080;
    
    var screenshotPromise;
    if (captureMethod === "none") {
        screenshotPromise = Promise.resolve({ screenshot: null });
    } else {
        screenshotPromise = fetch('/lvgl/screenshot', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
        body: JSON.stringify({
            capture: captureMethod,
            vnc_host: vncHost,
            vnc_port: parseInt(vncPort),
            qemu_window_titles: ["qemu-system", "qemu", "qemu-system-x86_64"]
        })
    }).then(response => {
            if (!response.ok) {
                return response.json().then(data => {
                    throw new Error(data.error || `HTTP error! status: ${response.status}`);
                });
            }
            return response.json();
        });
    }

    // First optionally capture screenshot using LVGL backend
    screenshotPromise
    .then(response => {
        if (response && response.error) {
            throw new Error(response.error);
        }

        if (response && response.screenshot) {
            var imgElement = document.getElementById("screenshot");
            imgElement.src = `data:image/png;base64, ${response.screenshot}`;
            if (response.fallback === "qemu_window_only") {
                setStatus("VNC capture failed, showing QEMU-window-only fallback screenshot.", "warn");
            }
        }

        var container = document.getElementById('container');
        container.style.display = 'grid';

        // Then get the LVGL tree structure
        return fetch('/lvgl/inspect', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                element: "root",
                max_depth: null,
                ip: lvglIp,
                port: lvglPort,
                capture: "none",
                vnc_host: vncHost,
                vnc_port: parseInt(vncPort),
                snapshot_path: "/tmp/lvgl_snapshot.png",
                deep_scan: true,
                scan_hidden: true,
                scan_extra_roots: true
            })
        });
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(data => {
                throw new Error(data.error || `HTTP error! status: ${response.status}`);
            });
        }
        return response.json();
    })
    .then(data => {
        // Check if the response contains an error
        if (data.error) {
            throw new Error(data.error);
        }
        
        // Update state with the tree data
        state.tree = data.tree;
        localStorage.setItem('inspect', JSON.stringify(data.tree));
        displayTree(data.tree);
        success = true;
    })
    .catch(error => {
        console.error('Error:', error);
        setStatus(error.message || "LVGL Inspection failed", "error");
    }).finally(() => {
        setLoading(false);
        var endTime = performance.now();
        var elapsedTime = endTime - startTime;
        var formattedElapsedTime = formatTime(elapsedTime);
        if (success) {
            setStatus(`Ready · ${formattedElapsedTime}`, "ok");
        }
        // Always ensure the button is enabled after the operation completes
        document.getElementById("btn_inspect").disabled = false;
    });
}

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
    toggle.className = "tree-toggle";
    toggle.textContent = hasChildren ? (expanded ? "▾" : "▸") : "";
    toggle.disabled = !hasChildren;
    toggle.setAttribute("aria-label", hasChildren ? "Toggle children" : "No children");
    if (!hasChildren) {
        toggle.classList.add("empty");
    }

    var button = document.createElement('button');
    button.type = "button";
    button.className = "tree-button";
    button.textContent = node.attributes.title || node.attributes.control_type || 'Unnamed Node';

    var meta = document.createElement('span');
    meta.className = "tree-meta";
    meta.textContent = node.attributes.control_type || "Unknown";

    button.addEventListener('click', function () {
        setActiveNode(node.idx);
    });

    toggle.addEventListener('click', function () {
        if (toggle.disabled) {
            return;
        }
        toggleVisibility(listItem, toggle);
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
        node.children.forEach(child => createTreeMenu(child, sublist, depth + 1));
        listItem.appendChild(sublist);
    }
}

function setNodeExpanded(element, expand) {
    var sublist = element.querySelector('.tree-children');
    if (!sublist) {
        return;
    }
    sublist.style.display = expand ? 'block' : 'none';
    element.dataset.expanded = expand ? "true" : "false";
    var toggle = element.querySelector('.tree-toggle');
    if (toggle && !toggle.disabled) {
        toggle.textContent = expand ? "▾" : "▸";
    }
    state.treeExpandedState[String(element.dataset.nodeId)] = !!expand;
    saveExpandedState();
}

function toggleVisibility(element, toggleControl) {
    var sublist = element.querySelector('.tree-children');
    if (sublist) {
        var isCollapsed = sublist.style.display === 'none';
        setNodeExpanded(element, isCollapsed);
        if (toggleControl) {
            toggleControl.textContent = isCollapsed ? "▾" : "▸";
        }
    }
}

function expandAllTree() {
    var nodes = document.querySelectorAll('.tree-item');
    nodes.forEach(function (node) {
        setNodeExpanded(node, true);
    });
}

function collapseAllTree() {
    var nodes = document.querySelectorAll('.tree-item');
    nodes.forEach(function (node, index) {
        setNodeExpanded(node, index === 0);
    });
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
    
    // Initialize with OpenCV inspector as default
    document.getElementById("opencvControls").style.display = "block";
    document.getElementById("lvglControls").style.display = "none";
    
    // Enable the inspect button by default
    document.getElementById("btn_inspect").disabled = false;
};

function releaseInspectButton() {
    var button = document.getElementById('btn_inspect');
    button.disabled = false;
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
