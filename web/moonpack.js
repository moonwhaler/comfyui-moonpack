import { app } from "../../scripts/app.js";

const MIN_INPUTS = 1;

// Both legacy v0.1 keys and the new MoonPack_* keys map to the same handlers
// so workflows saved before the rename keep working.
const DYNAMIC_INPUT_NODES = {
    "DynamicLoraStack":              { prefix: "lora_",  type: "WANVIDLORA" },
    "MoonPack_DynamicLoraStack":     { prefix: "lora_",  type: "WANVIDLORA" },
    "DynamicStringConcat":           { prefix: "input_", type: "STRING"     },
    "MoonPack_DynamicStringConcat":  { prefix: "input_", type: "STRING"     },
};
const FAST_BYPASSER_NODES = new Set(["FastNodeBypasser", "MoonPack_FastNodeBypasser"]);


function addDynamicInputSupport(nodeType, nodeData) {
    const { prefix, type } = DYNAMIC_INPUT_NODES[nodeData.name];

    nodeType.prototype.getDynInputs = function () {
        const inputs = (this.inputs || []).filter(
            (i) => i && i.name && i.name.startsWith(prefix),
        );
        inputs.sort((a, b) => {
            const ai = parseInt(a.name.split("_").pop(), 10);
            const bi = parseInt(b.name.split("_").pop(), 10);
            return ai - bi;
        });
        return inputs;
    };

    nodeType.prototype.stabilizeDynInputs = function () {
        if (!this.graph) return;
        let changed = false;

        // Trim trailing empty inputs (keep one empty at the very end).
        let dyn = this.getDynInputs();
        for (let i = dyn.length - 1; i > 0; i--) {
            if (dyn[i].link == null && dyn[i - 1].link == null) {
                this.removeInput(this.findInputSlot(dyn[i].name));
                changed = true;
            } else {
                break;
            }
        }
        dyn = this.getDynInputs();

        // Ensure exactly one trailing empty input.
        if (dyn.length === 0 || dyn[dyn.length - 1].link != null) {
            const next = dyn.length > 0
                ? parseInt(dyn[dyn.length - 1].name.split("_").pop(), 10) + 1
                : 1;
            this.addInput(`${prefix}${next}`, type);
            changed = true;
        }

        // Enforce minimum slot count.
        while (this.getDynInputs().length < MIN_INPUTS) {
            const next = this.getDynInputs().length + 1;
            this.addInput(`${prefix}${next}`, type);
            changed = true;
        }

        if (changed) this.setDirtyCanvas(true, true);
    };

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
        onNodeCreated?.apply(this, arguments);
        if (
            !this.inputs ||
            !this.inputs.some((i) => i.name && i.name.startsWith(prefix))
        ) {
            for (let i = 0; i < MIN_INPUTS; i++) {
                this.addInput(`${prefix}${i + 1}`, type);
            }
        }
        this.stabilizeDynInputs();
    };

    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
        onConfigure?.apply(this, arguments);
        this.stabilizeDynInputs();
    };

    const onConnectionsChange = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function () {
        onConnectionsChange?.apply(this, arguments);
        this.stabilizeDynInputs();
    };

    const onClone = nodeType.prototype.clone;
    nodeType.prototype.clone = function () {
        const cloned = onClone?.apply(this, arguments);
        if (cloned) {
            const onAdded = cloned.onAdded;
            cloned.onAdded = function () {
                onAdded?.apply(this, arguments);
                if (this.stabilizeDynInputs) this.stabilizeDynInputs();
            };
        }
        return cloned;
    };
}


function addFastNodeBypasserSupport(nodeType) {
    const MODE_ALWAYS = 0;
    const MODE_BYPASS = 4;
    const PROP_MATCH       = "matchTitle";
    const PROP_SORT        = "sort";
    const PROP_SORT_ALPHA  = "customSortAlphabet";
    const PROP_RESTRICT    = "toggleRestriction";

    nodeType["@matchTitle"] = { type: "string" };
    nodeType["@sort"] = {
        type: "combo",
        values: ["position", "alphanumeric", "custom alphabet"],
    };
    nodeType["@customSortAlphabet"] = { type: "string" };
    nodeType["@toggleRestriction"] = {
        type: "combo",
        values: ["default", "max one", "always one"],
    };

    nodeType.prototype._cachedRegex = function () {
        const pat = this.properties?.[PROP_MATCH]?.trim() || "";
        if (this._regexCacheKey === pat) return this._regexCache;
        this._regexCacheKey = pat;
        if (!pat) {
            this._regexCache = null;
        } else {
            try {
                this._regexCache = new RegExp(pat, "i");
            } catch (e) {
                console.error("[MoonPack] FastNodeBypasser invalid regex:", pat, e);
                this._regexCache = null;
            }
        }
        return this._regexCache;
    };

    nodeType.prototype.getConnectedNodes = function () {
        const out = [];
        if (!this.inputs) return out;
        for (const input of this.inputs) {
            if (input.link == null) continue;
            const link = app.graph.links[input.link];
            if (!link) continue;
            const origin = app.graph.getNodeById(link.origin_id);
            if (origin) out.push({ node: origin, inputIndex: this.inputs.indexOf(input) });
        }
        return out;
    };

    nodeType.prototype.getNodesToControl = function () {
        const regex = this._cachedRegex();
        let nodes;
        if (regex) {
            nodes = [];
            for (const n of (app.graph._nodes || [])) {
                if (n === this) continue;
                if (regex.exec(n.title || "")) {
                    nodes.push({ node: n, inputIndex: -1 });
                }
            }
        } else {
            nodes = this.getConnectedNodes();
        }

        const sort = this.properties?.[PROP_SORT] || "position";
        if (sort === "alphanumeric") {
            nodes.sort((a, b) => a.node.title.localeCompare(b.node.title));
        } else if (sort === "custom alphabet") {
            const raw = (this.properties?.[PROP_SORT_ALPHA] || "").replace(/\n/g, "");
            const alpha = raw.includes(",")
                ? raw.toLocaleLowerCase().split(",")
                : raw.toLocaleLowerCase().trim().split("");
            if (alpha?.length && alpha[0]) {
                nodes.sort((a, b) => {
                    const tA = a.node.title.toLocaleLowerCase();
                    const tB = b.node.title.toLocaleLowerCase();
                    let ai = -1, bi = -1;
                    for (let i = 0; i < alpha.length; i++) {
                        if (ai < 0 && tA.startsWith(alpha[i])) ai = i;
                        if (bi < 0 && tB.startsWith(alpha[i])) bi = i;
                        if (ai > -1 && bi > -1) break;
                    }
                    if (ai > -1 && bi > -1) {
                        return ai !== bi ? ai - bi : a.node.title.localeCompare(b.node.title);
                    } else if (ai > -1) return -1;
                    else if (bi > -1) return 1;
                    return a.node.title.localeCompare(b.node.title);
                });
            } else {
                nodes.sort((a, b) => a.node.title.localeCompare(b.node.title));
            }
        } else {
            // position
            nodes.sort((a, b) => {
                const dy = a.node.pos[1] - b.node.pos[1];
                if (Math.abs(dy) > 10) return dy;
                return a.node.pos[0] - b.node.pos[0];
            });
        }

        return nodes;
    };

    nodeType.prototype._applyRestriction = function (widget, value) {
        const restriction = this.properties?.[PROP_RESTRICT] || "default";
        if (value && restriction.includes(" one")) {
            for (const w of (this.widgets || [])) {
                if (w === widget || !w._controlledNodeId) continue;
                const other = app.graph.getNodeById(w._controlledNodeId);
                if (other) {
                    other.mode = MODE_BYPASS;
                    w.value = false;
                }
            }
        } else if (!value && restriction === "always one") {
            const anyOther = (this.widgets || []).some((w) => w !== widget && w.value);
            if (!anyOther) value = true;
        }
        return value;
    };

    nodeType.prototype.removeWidgetSafe = function (slot) {
        if (!this.widgets) return;
        const w = typeof slot === "number" ? this.widgets[slot] : slot;
        const idx = this.widgets.indexOf(w);
        if (idx !== -1) this.widgets.splice(idx, 1);
    };

    nodeType.prototype.stabilizeBypasser = function () {
        if (!this.graph) return;
        let changed = false;
        const nodes = this.getNodesToControl();
        const tempWidth = this.size[0];

        // Manage inputs only when in connection mode (no matchTitle).
        const useConnections = !this._cachedRegex();
        if (useConnections) {
            const last = this.inputs[this.inputs.length - 1];
            if (!last || last.link != null) {
                this.addInput(`bypass_node_${(this.inputs?.length) || 0}`, "*");
                changed = true;
            }
            for (let i = this.inputs.length - 2; i >= 0; i--) {
                if (this.inputs[i].link == null) {
                    this.removeInput(i);
                    changed = true;
                }
            }
            if (this.inputs.length === 0) {
                this.addInput("bypass_node_0", "*");
                changed = true;
            }
        } else {
            // Title-match mode: connection slots are unused, so hide them.
            for (let i = (this.inputs?.length || 0) - 1; i >= 0; i--) {
                if (this.inputs[i].name?.startsWith("bypass_node_")) {
                    this.removeInput(i);
                    changed = true;
                }
            }
        }

        const widgetCount = this.widgets ? this.widgets.length : 0;
        const nodeCount = nodes.length;

        // Add widgets for newly-controlled nodes.
        for (let i = widgetCount; i < nodeCount; i++) {
            const target = nodes[i].node;
            const widget = this.addWidget(
                "toggle",
                `Enable ${target.title}`,
                target.mode === MODE_ALWAYS,
                (val) => {
                    val = this._applyRestriction(widget, val);
                    target.mode = val ? MODE_ALWAYS : MODE_BYPASS;
                    widget.value = val;
                    app.graph.setDirtyCanvas(true, false);
                },
                { on: "active", off: "bypass" },
            );
            widget._controlledNodeId = target.id;
            changed = true;
        }

        // Drop excess widgets.
        while (this.widgets && this.widgets.length > nodeCount) {
            this.removeWidgetSafe(this.widgets.length - 1);
            changed = true;
        }

        // Sync remaining widgets with current target state.
        if (this.widgets) {
            for (let i = 0; i < this.widgets.length; i++) {
                const w = this.widgets[i];
                const target = nodes[i]?.node;
                if (!target) continue;
                const newName = `Enable ${target.title}`;
                const newVal = target.mode === MODE_ALWAYS;
                if (w.name !== newName) { w.name = newName; changed = true; }
                if (w.value !== newVal) { w.value = newVal; changed = true; }
                w._controlledNodeId = target.id;
                w.callback = (val) => {
                    val = this._applyRestriction(w, val);
                    target.mode = val ? MODE_ALWAYS : MODE_BYPASS;
                    w.value = val;
                    app.graph.setDirtyCanvas(true, false);
                };
            }
        }

        if (changed) {
            this.size[0] = Math.max(tempWidth, this.size[0]);
            this.setDirtyCanvas(true, true);
        }
    };

    nodeType.prototype.getExtraMenuOptions = function (_, options) {
        const nodes = this.getNodesToControl();
        const restriction = this.properties?.[PROP_RESTRICT] || "default";
        const onlyOne = restriction.includes(" one");
        const alwaysOne = restriction === "always one";

        options.unshift(
            {
                content: "Refresh",
                callback: () => {
                    this._regexCacheKey = undefined;
                    while (this.widgets && this.widgets.length > 0) this.removeWidgetSafe(0);
                    this.stabilizeBypasser();
                },
            },
            null,
        );

        if (nodes.length === 0) return;

        options.unshift(
            {
                content: "Bypass All",
                callback: () => {
                    for (let i = 0; i < nodes.length; i++) {
                        nodes[i].node.mode = (alwaysOne && i === 0) ? MODE_ALWAYS : MODE_BYPASS;
                    }
                    if (this.widgets) {
                        for (let i = 0; i < this.widgets.length; i++) {
                            this.widgets[i].value = (alwaysOne && i === 0);
                        }
                    }
                    app.graph.setDirtyCanvas(true, false);
                },
            },
            {
                content: "Enable All",
                callback: () => {
                    for (let i = 0; i < nodes.length; i++) {
                        nodes[i].node.mode = (onlyOne && i > 0) ? MODE_BYPASS : MODE_ALWAYS;
                    }
                    if (this.widgets) {
                        for (let i = 0; i < this.widgets.length; i++) {
                            this.widgets[i].value = !(onlyOne && i > 0);
                        }
                    }
                    app.graph.setDirtyCanvas(true, false);
                },
            },
            {
                content: "Toggle All",
                callback: () => {
                    let foundOne = false;
                    for (let i = 0; i < nodes.length; i++) {
                        const newVal = onlyOne && foundOne ? false : nodes[i].node.mode !== MODE_ALWAYS;
                        foundOne = foundOne || newVal;
                        nodes[i].node.mode = newVal ? MODE_ALWAYS : MODE_BYPASS;
                    }
                    if (!foundOne && alwaysOne && nodes.length > 0) {
                        nodes[nodes.length - 1].node.mode = MODE_ALWAYS;
                    }
                    if (this.widgets) {
                        for (let i = 0; i < this.widgets.length; i++) {
                            const t = nodes[i]?.node;
                            if (t) this.widgets[i].value = t.mode === MODE_ALWAYS;
                        }
                    }
                    app.graph.setDirtyCanvas(true, false);
                },
            },
            null,
        );
    };

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
        onNodeCreated?.apply(this, arguments);
        if (!this.properties) this.properties = {};
        if (this.properties[PROP_MATCH] === undefined)      this.properties[PROP_MATCH] = "";
        if (this.properties[PROP_SORT] === undefined)       this.properties[PROP_SORT] = "position";
        if (this.properties[PROP_SORT_ALPHA] === undefined) this.properties[PROP_SORT_ALPHA] = "";
        if (this.properties[PROP_RESTRICT] === undefined)   this.properties[PROP_RESTRICT] = "default";
        if (!this.inputs || this.inputs.length === 0) this.addInput("bypass_node_0", "*");
        this.stabilizeBypasser();
    };

    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
        onConfigure?.apply(this, arguments);
        this.stabilizeBypasser();
    };

    const onConnectionsChange = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function () {
        onConnectionsChange?.apply(this, arguments);
        this.stabilizeBypasser();
    };

    const onPropertyChanged = nodeType.prototype.onPropertyChanged;
    nodeType.prototype.onPropertyChanged = function (property) {
        onPropertyChanged?.apply(this, arguments);
        if (
            property === PROP_MATCH ||
            property === PROP_SORT ||
            property === PROP_SORT_ALPHA
        ) {
            this._regexCacheKey = undefined;
            while (this.widgets && this.widgets.length > 0) this.removeWidgetSafe(0);
            this.stabilizeBypasser();
        }
    };
}


app.registerExtension({
    name: "comfyui.moonpack.dynamic-inputs",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (DYNAMIC_INPUT_NODES[nodeData.name]) {
            addDynamicInputSupport(nodeType, nodeData);
        }
    },
});

app.registerExtension({
    name: "comfyui.moonpack.fast-bypasser",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (FAST_BYPASSER_NODES.has(nodeData.name)) {
            addFastNodeBypasserSupport(nodeType);
        }
    },
});
