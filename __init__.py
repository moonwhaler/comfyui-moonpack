from .proportional_dimension_node import NODE_CLASS_MAPPINGS as pd_class_mappings, NODE_DISPLAY_NAME_MAPPINGS as pd_display_mappings
from .string_replace_nodes import NODE_CLASS_MAPPINGS as sr_class_mappings, NODE_DISPLAY_NAME_MAPPINGS as sr_display_mappings
from .vace_looper_fade_mask_node import NODE_CLASS_MAPPINGS as vls_class_mappings, NODE_DISPLAY_NAME_MAPPINGS as vls_display_mappings
from .dynamic_string_concat_node import NODE_CLASS_MAPPINGS as dsc_class_mappings, NODE_DISPLAY_NAME_MAPPINGS as dsc_display_mappings
from .dynamic_lora_stack import NODE_CLASS_MAPPINGS as dls_class_mappings, NODE_DISPLAY_NAME_MAPPINGS as dls_display_mappings

# Combine the mappings
NODE_CLASS_MAPPINGS = {
    **dls_class_mappings,
    **dsc_class_mappings,
    **pd_class_mappings,
    **sr_class_mappings,
    **vls_class_mappings
}

NODE_DISPLAY_NAME_MAPPINGS = {
    **dls_display_mappings,
    **dsc_display_mappings,
    **pd_display_mappings,
    **sr_display_mappings,
    **vls_display_mappings
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']

print("### MoonPack Custom Nodes registered (Modular):")
for name in NODE_CLASS_MAPPINGS.keys():
    print(f"###   - {name}")
