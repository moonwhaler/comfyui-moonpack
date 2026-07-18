import logging

from .proportional_dimension_node import (
    NODE_CLASS_MAPPINGS as pd_class_mappings,
    NODE_DISPLAY_NAME_MAPPINGS as pd_display_mappings,
)
from .string_replace_nodes import (
    NODE_CLASS_MAPPINGS as sr_class_mappings,
    NODE_DISPLAY_NAME_MAPPINGS as sr_display_mappings,
)
from .vace_looper_fade_mask_node import (
    NODE_CLASS_MAPPINGS as vls_class_mappings,
    NODE_DISPLAY_NAME_MAPPINGS as vls_display_mappings,
)
from .dynamic_string_concat_node import (
    NODE_CLASS_MAPPINGS as dsc_class_mappings,
    NODE_DISPLAY_NAME_MAPPINGS as dsc_display_mappings,
)
from .dynamic_lora_stack_node import (
    NODE_CLASS_MAPPINGS as dls_class_mappings,
    NODE_DISPLAY_NAME_MAPPINGS as dls_display_mappings,
)
from .fast_node_bypasser import (
    NODE_CLASS_MAPPINGS as fnb_class_mappings,
    NODE_DISPLAY_NAME_MAPPINGS as fnb_display_mappings,
)
from .string_switch_node import (
    NODE_CLASS_MAPPINGS as ss_class_mappings,
    NODE_DISPLAY_NAME_MAPPINGS as ss_display_mappings,
)
from .conditional_bypasser_node import (
    NODE_CLASS_MAPPINGS as cb_class_mappings,
    NODE_DISPLAY_NAME_MAPPINGS as cb_display_mappings,
)
from .clean_save_image_node import (
    NODE_CLASS_MAPPINGS as csi_class_mappings,
    NODE_DISPLAY_NAME_MAPPINGS as csi_display_mappings,
)

log = logging.getLogger("MoonPack")

NODE_CLASS_MAPPINGS = {
    **pd_class_mappings,
    **sr_class_mappings,
    **vls_class_mappings,
    **dsc_class_mappings,
    **dls_class_mappings,
    **fnb_class_mappings,
    **ss_class_mappings,
    **cb_class_mappings,
    **csi_class_mappings,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    **pd_display_mappings,
    **sr_display_mappings,
    **vls_display_mappings,
    **dsc_display_mappings,
    **dls_display_mappings,
    **fnb_display_mappings,
    **ss_display_mappings,
    **cb_display_mappings,
    **csi_display_mappings,
}

# Legacy aliases keep workflows saved with v0.1 keys loadable. Remove in 1.0.
LEGACY_ALIASES = {
    "ProportionalDimension":      "MoonPack_ProportionalDimension",
    "SimpleStringReplace":        "MoonPack_SimpleStringReplace",
    "RegexStringReplace":         "MoonPack_RegexStringReplace",
    "DynamicStringConcat":        "MoonPack_DynamicStringConcat",
    "DynamicLoraStack":           "MoonPack_DynamicLoraStack",
    "FastNodeBypasser":           "MoonPack_FastNodeBypasser",
    "VACELooperFrameMaskCreator": "MoonPack_VACELooperFrameMaskCreator",
}
for _old, _new in LEGACY_ALIASES.items():
    if _new in NODE_CLASS_MAPPINGS:
        NODE_CLASS_MAPPINGS[_old] = NODE_CLASS_MAPPINGS[_new]
        NODE_DISPLAY_NAME_MAPPINGS[_old] = NODE_DISPLAY_NAME_MAPPINGS[_new] + " (legacy)"

WEB_DIRECTORY = "./web"
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]

log.info(
    "MoonPack registered %d nodes (+ %d legacy aliases)",
    len(NODE_CLASS_MAPPINGS) - len(LEGACY_ALIASES),
    len(LEGACY_ALIASES),
)
