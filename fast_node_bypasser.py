from .utils import any_type


class FastNodeBypasser:
    """
    A node that allows quick bypassing of connected nodes.
    Connect any nodes to this bypasser, and it will create toggle controls for each.
    """

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {},
            "optional": {},
        }

    RETURN_TYPES = (any_type,)
    RETURN_NAMES = ("*",)
    FUNCTION = "bypass_nodes"
    CATEGORY = "moonpack/utils"
    OUTPUT_NODE = False

    # This is a virtual node - it doesn't do any actual processing
    # All the logic is handled on the frontend (JavaScript)

    def bypass_nodes(self, **kwargs):
        """
        This node is a passthrough/virtual node.
        The actual bypassing logic is handled in the JavaScript frontend.
        """
        # Return None as this is a control node, not a data processing node
        return (None,)


NODE_CLASS_MAPPINGS = {
    "FastNodeBypasser": FastNodeBypasser
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FastNodeBypasser": "Fast Node Bypasser"
}
