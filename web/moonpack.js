import { app } from "/scripts/app.js";

const MIN_INPUTS = 2;
const OVERRIDDEN_NODES = new Map();

/**
 * Base class for our dynamic nodes, handles the override registration.
 */
class MoonpackBaseNode {
    static registerForOverride(nodeType, nodeData, customClass) {
        OVERRIDDEN_NODES.set(nodeType, customClass);
        customClass.nodeType = nodeType;
        customClass.nodeData = nodeData;
    }
}

/**
 * Creates a new custom node class that handles dynamic inputs.
 * @param {object} nodeType The original node class from LiteGraph.
 * @param {object} nodeData The node's registration data.
 */
function createDynamicNodeClass(nodeType, nodeData) {
    const input_prefix = nodeData.name === "DynamicLoraStack" ? "lora_" : "input_";
    const input_type = nodeData.name === "DynamicLoraStack" ? "WANVIDLORA" : "STRING";

    class MoonpackDynamicNode extends nodeType {
        constructor() {
            super();
            this.title = this.constructor.title;
            // Add initial inputs right after construction.
            for (let i = 0; i < MIN_INPUTS; i++) {
                this.addInput(`${input_prefix}${i + 1}`, input_type);
            }
            this.stabilize();
        }

        onConnectionsChange(type, index, connected, linkInfo, ioSlot) {
            // Call the original method if it exists
            super.onConnectionsChange?.(type, index, connected, linkInfo, ioSlot);
            if (type === LiteGraph.INPUT) {
                this.stabilize();
            }
        }

        getOptionalInputs() {
            return this.inputs?.filter(i => i.name.startsWith(input_prefix)) || [];
        }

        stabilize() {
            const optionalInputs = this.getOptionalInputs();
            let changed = false;

            // Add a new input if the last one is connected.
            if (optionalInputs.length === 0 || optionalInputs[optionalInputs.length - 1].link != null) {
                const nextIndex = optionalInputs.length + 1;
                this.addInput(`${input_prefix}${nextIndex}`, input_type);
                changed = true;
            }

            // Remove disconnected inputs from the end, but maintain the minimum.
            for (let i = optionalInputs.length - 1; i >= MIN_INPUTS; i--) {
                if (optionalInputs[i].link == null) {
                    const inputToRemove = this.inputs.find(input => input.name === optionalInputs[i].name);
                    if (inputToRemove) {
                        this.removeInput(this.inputs.indexOf(inputToRemove));
                        changed = true;
                    }
                } else {
                    break; // Stop at the first connected input from the end.
                }
            }

            if (changed) {
                this.setDirtyCanvas(true, true);
            }
        }
    }

    MoonpackDynamicNode.title = nodeData.display_name;
    return MoonpackDynamicNode;
}

// Monkey-patch LiteGraph to hijack node registration
const original_registerNodeType = LiteGraph.registerNodeType;
LiteGraph.registerNodeType = function(nodeId, baseClass) {
    const customClass = OVERRIDDEN_NODES.get(baseClass);
    return original_registerNodeType.call(this, nodeId, customClass || baseClass);
};

app.registerExtension({
    name: "comfyui.moonpack.dynamicNodes",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "DynamicLoraStack" || nodeData.name === "DynamicStringConcat") {
            const dynamicNodeClass = createDynamicNodeClass(nodeType, nodeData);
            MoonpackBaseNode.registerForOverride(nodeType, nodeData, dynamicNodeClass);
        }
    },
});
