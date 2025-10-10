import { app } from "/scripts/app.js";

const MIN_INPUTS = 1;

/**
 * Adds dynamic input handling to a node type.
 * @param {object} nodeType The node class to modify.
 * @param {object} nodeData The node's registration data.
 */
function addDynamicInputSupport(nodeType, nodeData) {
    const input_prefix = nodeData.name === "DynamicLoraStack" ? "lora_" : "input_";
    const input_type = nodeData.name === "DynamicLoraStack" ? "WANVIDLORA" : "STRING";

    // --- Add state and a polling stabilizer to the node's prototype ---
    nodeType.prototype.schedulePromise = null;

    nodeType.prototype.scheduleStabilize = function(ms = 100) {
        if (!this.schedulePromise) {
            this.schedulePromise = new Promise((resolve) => {
                setTimeout(() => {
                    this.schedulePromise = null;
                    this.stabilize();
                    resolve();
                }, ms);
            });
        }
        return this.schedulePromise;
    };

    nodeType.prototype.stabilize = function() {
        let optionalInputs = this.getOptionalInputs();
        let changed = false;

        // Ensure there's always one empty input at the end.
        if (optionalInputs.length === 0 || optionalInputs[optionalInputs.length - 1].link != null) {
            const nextIndex = optionalInputs.length > 0 ? parseInt(optionalInputs[optionalInputs.length - 1].name.split('_').pop(), 10) + 1 : 1;
            this.addInput(`${input_prefix}${nextIndex}`, input_type);
            changed = true;
            optionalInputs = this.getOptionalInputs(); // Refresh after adding
        }

        // Clean up any disconnected inputs from the end, but always leave at least one.
        for (let i = optionalInputs.length - 2; i >= 0; i--) {
            if (optionalInputs[i].link == null && optionalInputs[i+1].link == null) {
                this.removeInput(this.findInputSlot(optionalInputs[i].name));
                changed = true;
            } else {
                break;
            }
        }

        // Ensure minimum inputs are present.
        while (this.getOptionalInputs().length < MIN_INPUTS) {
            const nextIndex = this.getOptionalInputs().length + 1;
            this.addInput(`${input_prefix}${nextIndex}`, input_type);
            changed = true;
        }

        if (changed) {
            this.setDirtyCanvas(true, true);
        }

        // Re-schedule the next check to create the self-correcting loop.
        this.scheduleStabilize(500);
    };

    nodeType.prototype.getOptionalInputs = function() {
        const inputs = this.inputs?.filter(i => i.name.startsWith(input_prefix)) || [];
        inputs.sort((a, b) => {
            const a_index = parseInt(a.name.split('_').pop(), 10);
            const b_index = parseInt(b.name.split('_').pop(), 10);
            return a_index - b_index;
        });
        return inputs;
    };

    // --- Hijack existing methods to add our logic ---

    // When a node is created, set it up and start the stabilizer.
    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function() {
        onNodeCreated?.apply(this, arguments);
        // Add initial inputs if they don't exist.
        if (!this.inputs || this.inputs.filter(i => i.name.startsWith(input_prefix)).length === 0) {
             for (let i = 0; i < MIN_INPUTS; i++) {
                this.addInput(`${input_prefix}${i + 1}`, input_type);
            }
        }
        this.scheduleStabilize();
    };

    // Any connection change should trigger a stabilization check.
    const onConnectionsChange = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function() {
        onConnectionsChange?.apply(this, arguments);
        this.scheduleStabilize();
    };
    
    // When cloning, ensure the new node is also stabilized.
    const onClone = nodeType.prototype.clone;
    nodeType.prototype.clone = function() {
        const cloned = onClone?.apply(this, arguments);
        if (cloned) {
            // Use a timeout to ensure the clone is fully added to the graph before stabilizing.
            setTimeout(() => {
                if(cloned.scheduleStabilize) {
                    cloned.scheduleStabilize();
                }
            }, 200);
        }
        return cloned;
    };
}

/**
 * Adds fast node bypasser functionality
 * @param {object} nodeType The node class to modify
 * @param {object} nodeData The node's registration data
 */
function addFastNodeBypasserSupport(nodeType, nodeData) {
    const MODE_ALWAYS = 0;
    const MODE_BYPASS = 4;
    const PROPERTY_MATCH_TITLE = "matchTitle";
    const PROPERTY_SORT = "sort";
    const PROPERTY_SORT_CUSTOM_ALPHA = "customSortAlphabet";
    const PROPERTY_RESTRICTION = "toggleRestriction";

    // Define properties following the exact same pattern as fast groups bypasser
    nodeType["@matchTitle"] = { type: "string" };
    nodeType["@sort"] = {
        type: "combo",
        values: ["position", "alphanumeric", "custom alphabet"]
    };
    nodeType["@customSortAlphabet"] = { type: "string" };
    nodeType["@toggleRestriction"] = {
        type: "combo",
        values: ["default", "max one", "always one"]
    };

    nodeType.prototype.schedulePromise = null;

    nodeType.prototype.scheduleStabilize = function(ms = 100) {
        if (!this.schedulePromise) {
            this.schedulePromise = new Promise((resolve) => {
                setTimeout(() => {
                    this.schedulePromise = null;
                    this.stabilize();
                    resolve();
                }, ms);
            });
        }
        return this.schedulePromise;
    };

    nodeType.prototype.getConnectedNodes = function() {
        const connectedNodes = [];
        if (!this.inputs) return connectedNodes;

        for (const input of this.inputs) {
            if (input.link != null) {
                const link = app.graph.links[input.link];
                if (link) {
                    const originNode = app.graph.getNodeById(link.origin_id);
                    if (originNode) {
                        connectedNodes.push({
                            node: originNode,
                            inputIndex: this.inputs.indexOf(input)
                        });
                    }
                }
            }
        }
        return connectedNodes;
    };

    nodeType.prototype.getNodesToControl = function() {
        // If matchTitle is set, use pattern matching instead of connections
        const matchTitle = this.properties?.[PROPERTY_MATCH_TITLE]?.trim();
        let nodesToControl = [];

        if (matchTitle) {
            const matchedNodes = [];
            try {
                const regex = new RegExp(matchTitle, "i");
                const allNodes = app.graph._nodes || [];

                for (const node of allNodes) {
                    // Don't match ourselves
                    if (node === this) continue;

                    if (regex.exec(node.title)) {
                        matchedNodes.push({
                            node: node,
                            inputIndex: -1 // Not connected via input
                        });
                    }
                }
            } catch (e) {
                console.error("Invalid regex pattern in matchTitle:", e);
            }
            nodesToControl = matchedNodes;
        } else {
            // Otherwise, use the traditional connection-based approach
            nodesToControl = this.getConnectedNodes();
        }

        // Apply sorting
        const sort = this.properties?.[PROPERTY_SORT] || "position";

        if (sort === "alphanumeric") {
            nodesToControl.sort((a, b) => a.node.title.localeCompare(b.node.title));
        } else if (sort === "custom alphabet") {
            let customAlphabet = null;
            const customAlphaStr = this.properties?.[PROPERTY_SORT_CUSTOM_ALPHA]?.replace(/\n/g, "");
            if (customAlphaStr && customAlphaStr.trim()) {
                customAlphabet = customAlphaStr.includes(",")
                    ? customAlphaStr.toLocaleLowerCase().split(",")
                    : customAlphaStr.toLocaleLowerCase().trim().split("");
            }

            if (customAlphabet?.length) {
                nodesToControl.sort((a, b) => {
                    let aIndex = -1;
                    let bIndex = -1;
                    // Loop and find indexes
                    for (const [index, alpha] of customAlphabet.entries()) {
                        aIndex = aIndex < 0 ? (a.node.title.toLocaleLowerCase().startsWith(alpha) ? index : -1) : aIndex;
                        bIndex = bIndex < 0 ? (b.node.title.toLocaleLowerCase().startsWith(alpha) ? index : -1) : bIndex;
                        if (aIndex > -1 && bIndex > -1) {
                            break;
                        }
                    }
                    // Now compare
                    if (aIndex > -1 && bIndex > -1) {
                        const ret = aIndex - bIndex;
                        if (ret === 0) {
                            return a.node.title.localeCompare(b.node.title);
                        }
                        return ret;
                    } else if (aIndex > -1) {
                        return -1;
                    } else if (bIndex > -1) {
                        return 1;
                    }
                    return a.node.title.localeCompare(b.node.title);
                });
            } else {
                // Fallback to alphanumeric if custom alphabet is invalid
                nodesToControl.sort((a, b) => a.node.title.localeCompare(b.node.title));
            }
        } else if (sort === "position") {
            nodesToControl.sort((a, b) => {
                // Sort by Y position first, then X position
                const yDiff = a.node.pos[1] - b.node.pos[1];
                if (Math.abs(yDiff) > 10) { // Use threshold for "same row"
                    return yDiff;
                }
                return a.node.pos[0] - b.node.pos[0];
            });
        }

        return nodesToControl;
    };

    nodeType.prototype.stabilize = function() {
        if (!this.graph) return;

        let changed = false;
        const nodesToControl = this.getNodesToControl();

        // Store current width to preserve it during changes
        const tempWidth = this.size[0];

        // Only manage inputs if we're using connection-based mode (not matchTitle)
        const matchTitle = this.properties?.[PROPERTY_MATCH_TITLE]?.trim();
        if (!matchTitle) {
            // Ensure we have enough inputs (always one empty at the end)
            const lastInput = this.inputs[this.inputs.length - 1];
            if (!lastInput || lastInput.link != null) {
                this.addInput(`bypass_node_${this.inputs.length}`, "*");
                changed = true;
            }

            // Remove empty inputs from the middle
            for (let i = this.inputs.length - 2; i >= 0; i--) {
                if (this.inputs[i].link == null) {
                    this.removeInput(i);
                    changed = true;
                }
            }

            // Ensure at least one input exists
            if (this.inputs.length === 0) {
                this.addInput("bypass_node_0", "*");
                changed = true;
            }
        }

        // Update widgets to match nodes to control
        const widgetCount = this.widgets ? this.widgets.length : 0;
        const nodeCount = nodesToControl.length;

        // Add widgets for new nodes
        for (let i = widgetCount; i < nodeCount; i++) {
            const controlledNode = nodesToControl[i].node;
            const widget = this.addWidget(
                "toggle",
                `Enable ${controlledNode.title}`,
                controlledNode.mode === MODE_ALWAYS,
                (value) => {
                    // Handle toggle restriction
                    const restriction = this.properties?.[PROPERTY_RESTRICTION] || "default";

                    if (value && restriction?.includes(" one")) {
                        // If enabling and we have a "max one" or "always one" restriction, disable all others
                        for (const w of this.widgets) {
                            if (w !== widget && w._controlledNodeId) {
                                const otherNode = app.graph.getNodeById(w._controlledNodeId);
                                if (otherNode) {
                                    otherNode.mode = MODE_BYPASS;
                                    w.value = false;
                                }
                            }
                        }
                    } else if (!value && restriction === "always one") {
                        // If disabling and we have "always one" restriction, check if we're the last one
                        const anyEnabled = this.widgets.some(w => w !== widget && w.value);
                        if (!anyEnabled) {
                            // Don't allow disabling the last one
                            value = true;
                        }
                    }

                    // Toggle the node's mode
                    controlledNode.mode = value ? MODE_ALWAYS : MODE_BYPASS;
                    widget.value = value; // Ensure widget reflects the final state
                    app.graph.setDirtyCanvas(true, false);
                },
                { on: "active", off: "bypass" }
            );
            widget._controlledNodeId = controlledNode.id;
            changed = true;
        }

        // Remove excess widgets
        while (this.widgets && this.widgets.length > nodeCount) {
            this.removeWidget(this.widgets.length - 1);
            changed = true;
        }

        // Update existing widgets
        if (this.widgets) {
            for (let i = 0; i < this.widgets.length; i++) {
                const widget = this.widgets[i];
                const controlledNode = nodesToControl[i]?.node;

                if (controlledNode) {
                    const newName = `Enable ${controlledNode.title}`;
                    const newValue = controlledNode.mode === MODE_ALWAYS;

                    if (widget.name !== newName) {
                        widget.name = newName;
                        changed = true;
                    }

                    if (widget.value !== newValue) {
                        widget.value = newValue;
                        changed = true;
                    }

                    widget._controlledNodeId = controlledNode.id;

                    // Update the callback to reference the current node and handle restrictions
                    widget.callback = (value) => {
                        // Handle toggle restriction
                        const restriction = this.properties?.[PROPERTY_RESTRICTION] || "default";

                        if (value && restriction?.includes(" one")) {
                            // If enabling and we have a "max one" or "always one" restriction, disable all others
                            for (const w of this.widgets) {
                                if (w !== widget && w._controlledNodeId) {
                                    const otherNode = app.graph.getNodeById(w._controlledNodeId);
                                    if (otherNode) {
                                        otherNode.mode = MODE_BYPASS;
                                        w.value = false;
                                    }
                                }
                            }
                        } else if (!value && restriction === "always one") {
                            // If disabling and we have "always one" restriction, check if we're the last one
                            const anyEnabled = this.widgets.some(w => w !== widget && w.value);
                            if (!anyEnabled) {
                                // Don't allow disabling the last one
                                value = true;
                            }
                        }

                        // Toggle the node's mode
                        controlledNode.mode = value ? MODE_ALWAYS : MODE_BYPASS;
                        widget.value = value; // Ensure widget reflects the final state
                        app.graph.setDirtyCanvas(true, false);
                    };
                }
            }
        }

        // Restore width
        if (changed) {
            this.size[0] = Math.max(tempWidth, this.size[0]);
            this.setDirtyCanvas(true, true);
        }

        // Schedule next stabilization
        this.scheduleStabilize(500);
    };

    // Add context menu actions
    nodeType.prototype.getExtraMenuOptions = function(_, options) {
        const nodesToControl = this.getNodesToControl();

        if (nodesToControl.length > 0) {
            options.unshift(
                {
                    content: "Bypass All",
                    callback: () => {
                        const restriction = this.properties?.[PROPERTY_RESTRICTION] || "default";
                        const alwaysOne = restriction === "always one";

                        for (let i = 0; i < nodesToControl.length; i++) {
                            const {node} = nodesToControl[i];
                            // If "always one" restriction, enable the first, bypass the rest
                            node.mode = (alwaysOne && i === 0) ? MODE_ALWAYS : MODE_BYPASS;
                        }
                        if (this.widgets) {
                            for (let i = 0; i < this.widgets.length; i++) {
                                this.widgets[i].value = (alwaysOne && i === 0);
                            }
                        }
                        app.graph.setDirtyCanvas(true, false);
                    }
                },
                {
                    content: "Enable All",
                    callback: () => {
                        const restriction = this.properties?.[PROPERTY_RESTRICTION] || "default";
                        const onlyOne = restriction?.includes(" one");

                        for (let i = 0; i < nodesToControl.length; i++) {
                            const {node} = nodesToControl[i];
                            // If restriction includes "one", only enable the first
                            node.mode = (onlyOne && i > 0) ? MODE_BYPASS : MODE_ALWAYS;
                        }
                        if (this.widgets) {
                            for (let i = 0; i < this.widgets.length; i++) {
                                this.widgets[i].value = !(onlyOne && i > 0);
                            }
                        }
                        app.graph.setDirtyCanvas(true, false);
                    }
                },
                {
                    content: "Toggle All",
                    callback: () => {
                        const restriction = this.properties?.[PROPERTY_RESTRICTION] || "default";
                        const onlyOne = restriction?.includes(" one");
                        let foundOne = false;

                        for (let i = 0; i < nodesToControl.length; i++) {
                            const {node} = nodesToControl[i];
                            // If you have only one, then we'll stop at the first
                            let newValue = onlyOne && foundOne ? false : node.mode !== MODE_ALWAYS;
                            foundOne = foundOne || newValue;
                            node.mode = newValue ? MODE_ALWAYS : MODE_BYPASS;
                        }

                        // And if you have always one, then we'll flip the last
                        if (!foundOne && restriction === "always one" && nodesToControl.length > 0) {
                            nodesToControl[nodesToControl.length - 1].node.mode = MODE_ALWAYS;
                        }

                        if (this.widgets) {
                            for (let i = 0; i < this.widgets.length; i++) {
                                const widget = this.widgets[i];
                                const controlledNode = nodesToControl[i]?.node;
                                if (controlledNode) {
                                    widget.value = controlledNode.mode === MODE_ALWAYS;
                                }
                            }
                        }
                        app.graph.setDirtyCanvas(true, false);
                    }
                },
                null // separator
            );
        }
    };

    // Initialize on node creation
    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function() {
        onNodeCreated?.apply(this, arguments);

        // Initialize properties following the exact same pattern as fast groups bypasser
        if (!this.properties) {
            this.properties = {};
        }
        if (this.properties[PROPERTY_MATCH_TITLE] === undefined) {
            this.properties[PROPERTY_MATCH_TITLE] = "";
        }
        if (this.properties[PROPERTY_SORT] === undefined) {
            this.properties[PROPERTY_SORT] = "position";
        }
        if (this.properties[PROPERTY_SORT_CUSTOM_ALPHA] === undefined) {
            this.properties[PROPERTY_SORT_CUSTOM_ALPHA] = "";
        }
        if (this.properties[PROPERTY_RESTRICTION] === undefined) {
            this.properties[PROPERTY_RESTRICTION] = "default";
        }

        // Add initial input if none exist
        if (!this.inputs || this.inputs.length === 0) {
            this.addInput("bypass_node_0", "*");
        }

        this.scheduleStabilize();
    };

    // Handle connection changes
    const onConnectionsChange = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function(type, index, connected, link_info) {
        onConnectionsChange?.apply(this, arguments);
        this.scheduleStabilize();
    };

    // Handle removal of widgets
    nodeType.prototype.removeWidget = function(slot) {
        if (this.widgets) {
            const widget = typeof slot === "number" ? this.widgets[slot] : slot;
            const index = this.widgets.indexOf(widget);
            if (index !== -1) {
                this.widgets.splice(index, 1);
            }
        }
    };

    // Handle property changes (e.g., when matchTitle or sort is updated)
    const onPropertyChanged = nodeType.prototype.onPropertyChanged;
    nodeType.prototype.onPropertyChanged = function(property, value) {
        onPropertyChanged?.apply(this, arguments);
        if (property === PROPERTY_MATCH_TITLE || property === PROPERTY_SORT || property === PROPERTY_SORT_CUSTOM_ALPHA) {
            // Clear all widgets and refresh when matchTitle or sort changes
            while (this.widgets && this.widgets.length > 0) {
                this.removeWidget(0);
            }
            this.scheduleStabilize(10); // Quick refresh
        }
    };
}

app.registerExtension({
    name: "comfyui.moonpack.dynamicNodes",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "DynamicLoraStack" || nodeData.name === "DynamicStringConcat") {
            addDynamicInputSupport(nodeType, nodeData);
        }

        if (nodeData.name === "FastNodeBypasser") {
            addFastNodeBypasserSupport(nodeType, nodeData);
        }
    },
});
