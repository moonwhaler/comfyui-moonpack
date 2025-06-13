from .proportional_dimension_node import NODE_CLASS_MAPPINGS as pd_class_mappings, NODE_DISPLAY_NAME_MAPPINGS as pd_display_mappings
from .string_replace_nodes import NODE_CLASS_MAPPINGS as sr_class_mappings, NODE_DISPLAY_NAME_MAPPINGS as sr_display_mappings
from .vace_looper_scheduler_node import NODE_CLASS_MAPPINGS as vls_class_mappings, NODE_DISPLAY_NAME_MAPPINGS as vls_display_mappings

# Combine the mappings
NODE_CLASS_MAPPINGS = {
    **pd_class_mappings,
    **sr_class_mappings,
    **vls_class_mappings
}

NODE_DISPLAY_NAME_MAPPINGS = {
    **pd_display_mappings,
    **sr_display_mappings,
    **vls_display_mappings
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']

print("### MoonPack Custom Nodes registered (Modular):")
for name in NODE_CLASS_MAPPINGS.keys():
    print(f"###   - {name}")
