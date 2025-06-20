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
            "required": {},
            "optional": {
                "input_1": ("STRING", {"multiline": True, "default": ""}),
                "input_2": ("STRING", {"multiline": True, "default": ""}),
                "input_3": ("STRING", {"multiline": True, "default": ""}),
                "input_4": ("STRING", {"multiline": True, "default": ""}),
                "input_5": ("STRING", {"multiline": True, "default": ""}),
                "separator": ("STRING", {"default": " ", "multiline": False}),
                "ignore_empty": ("BOOLEAN", {"default": True}),
            }
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
        
        # Durchlaufe alle bereitgestellten Keyword-Argumente
        for key, value in kwargs.items():
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