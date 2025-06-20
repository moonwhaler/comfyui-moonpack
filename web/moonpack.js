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

app.registerExtension({
    name: "comfyui.moonpack.dynamicNodes",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "DynamicLoraStack" || nodeData.name === "DynamicStringConcat") {
            addDynamicInputSupport(nodeType, nodeData);
        }
    },
});
