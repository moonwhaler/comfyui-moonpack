from .utils import FlexibleOptionalInputType
import re

class DynamicStringConcat:
    """
    Eine dynamische String-Concat-Node, die automatisch neue Inputs hinzufügt,
    sobald alle vorhandenen Inputs belegt sind, ähnlich wie die rgthree Any Switch Node.
    """
    
    def __init__(self):
        pass
        
    @classmethod
    def INPUT_TYPES(cls):
        """
        Definiert die Input-Typen für die Node.
        Die Anzahl der Inputs wird dynamisch erweitert.
        """
        return {
            "required": {
                "separator": ("STRING", {"default": " ", "multiline": False}),
                "ignore_empty": ("BOOLEAN", {"default": True}),
            },
            "optional": FlexibleOptionalInputType("STRING")
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("concatenated_string",)
    FUNCTION = "concatenate_strings"
    CATEGORY = "utils"
    OUTPUT_NODE = False
    
    def concatenate_strings(self, separator=" ", ignore_empty=True, **kwargs):
        """
        Führt alle bereitgestellten String-Inputs zusammen.
        
        Args:
            separator (str): Trennzeichen zwischen den Strings
            ignore_empty (bool): Ob leere Strings ignoriert werden sollen
            **kwargs: Alle Input-Strings
            
        Returns:
            tuple: (zusammengeführter String)
        """
        # Sammle alle Input-Strings
        inputs = []
        
        # Sortiere die Inputs numerisch, um die korrekte Reihenfolge sicherzustellen
        sorted_items = sorted(kwargs.items(), key=lambda item: int(item[0].split('_')[1]) if item[0].startswith("input_") else -1)

        for key, value in sorted_items:
            if key.startswith("input_") and value is not None:
                if isinstance(value, (list, tuple)):
                    # Falls es ein Array ist, nimm das erste Element
                    value = value[0] if len(value) > 0 else ""
                
                # Wandle zu String um
                str_value = str(value).strip()
                
                # Füge hinzu, wenn nicht leer oder wenn leere Strings nicht ignoriert werden
                if str_value or not ignore_empty:
                    inputs.append(str_value)
        
        # Führe alle Strings zusammen
        result = separator.join(inputs)
        
        print(f"Dynamic String Concat: Concatenated {len(inputs)} inputs: '{result}'")
        
        return (result,)


# Node-Mappings für ComfyUI
NODE_CLASS_MAPPINGS = {
    "DynamicStringConcat": DynamicStringConcat
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DynamicStringConcat": "Dynamic String Concat"
}
