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

    // Define properties following the exact same pattern as fast groups bypasser
    nodeType["@matchTitle"] = { type: "string" };

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
            return matchedNodes;
        }

        // Otherwise, use the traditional connection-based approach
        return this.getConnectedNodes();
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
                this.addInput(`node_${this.inputs.length}`, "*");
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
                this.addInput("node_0", "*");
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
                    // Toggle the node's mode
                    controlledNode.mode = value ? MODE_ALWAYS : MODE_BYPASS;
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

                    // Update the callback to reference the current node
                    widget.callback = (value) => {
                        controlledNode.mode = value ? MODE_ALWAYS : MODE_BYPASS;
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
                        for (const {node} of nodesToControl) {
                            node.mode = MODE_BYPASS;
                        }
                        if (this.widgets) {
                            for (const widget of this.widgets) {
                                widget.value = false;
                            }
                        }
                        app.graph.setDirtyCanvas(true, false);
                    }
                },
                {
                    content: "Enable All",
                    callback: () => {
                        for (const {node} of nodesToControl) {
                            node.mode = MODE_ALWAYS;
                        }
                        if (this.widgets) {
                            for (const widget of this.widgets) {
                                widget.value = true;
                            }
                        }
                        app.graph.setDirtyCanvas(true, false);
                    }
                },
                {
                    content: "Toggle All",
                    callback: () => {
                        for (const {node} of nodesToControl) {
                            node.mode = node.mode === MODE_ALWAYS ? MODE_BYPASS : MODE_ALWAYS;
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

        // Add initial input if none exist
        if (!this.inputs || this.inputs.length === 0) {
            this.addInput("node_0", "*");
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

    // Handle property changes (e.g., when matchTitle is updated)
    const onPropertyChanged = nodeType.prototype.onPropertyChanged;
    nodeType.prototype.onPropertyChanged = function(property, value) {
        onPropertyChanged?.apply(this, arguments);
        if (property === PROPERTY_MATCH_TITLE) {
            // Clear all widgets and refresh when matchTitle changes
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
