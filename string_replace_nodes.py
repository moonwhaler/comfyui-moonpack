import re
from typing import Tuple

HELP_TEXT = """Examples:
Find => Replace pairs (one per line):
hello => hi
world => earth
old => new

Empty replacement removes text:
remove_this => 

Note: Replacements are applied sequentially.
If 'A => B' and 'B => C' are pairs, 'A' will become 'C'."""

REGEX_HELP = """Common Patterns:
. = any character
.* = any characters
\\d = digit
\\w = word character
[abc] = a, b, or c
(text) = capture group
"""

class SimpleStringReplace:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "text": ("STRING", {"multiline": True}),
                "find_replace_pairs": ("STRING", {
                    "multiline": True,
                    "default": "find => replace\nold => new",
                    "placeholder": HELP_TEXT
                }),
            },
        }
    
    RETURN_TYPES = ("STRING",)
    FUNCTION = "replace"
    CATEGORY = "string"

    def replace(self, text: str, find_replace_pairs: str) -> Tuple[str]:
        if not text:
            return (text,)

        result = text
        lines = [line.strip() for line in find_replace_pairs.split('\n') if line.strip()]
        
        for line in lines:
            if '=>' not in line:
                continue
                
            find, replace = line.split('=>', 1)
            find = find.strip()
            replace = replace.strip()
            
            if find:  # Only replace if find pattern is not empty
                result = result.replace(find, replace)
        
        return (result,)

class RegexStringReplace:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "text": ("STRING", {"multiline": True}),
                "pattern": ("STRING", {
                    "multiline": True,
                    "placeholder": REGEX_HELP
                }),
                "replacement": ("STRING", {"multiline": True}),
            },
            "optional": {
                "case_insensitive": ("BOOLEAN", {"default": False}),
                "test_mode": ("BOOLEAN", {"default": False}),
            }
        }
    
    RETURN_TYPES = ("STRING",)
    FUNCTION = "replace"
    CATEGORY = "string"

    def replace(self, text: str, pattern: str, replacement: str, 
                case_insensitive: bool = False, test_mode: bool = False) -> Tuple[str]:
        if not text or not pattern:
            return (text,)
            
        try:
            flags = re.IGNORECASE if case_insensitive else 0
            
            if test_mode:
                # In test mode, highlight matches without replacing
                matches = re.finditer(pattern, text, flags=flags)
                result = text
                highlight_start = ">>>"
                highlight_end = "<<<"
                
                # Work backwards through matches to not mess up positions
                matches = list(matches)
                for match in reversed(matches):
                    start, end = match.span()
                    result = result[:start] + highlight_start + result[start:end] + highlight_end + result[end:]
                    
                return (result,)
            else:
                result = re.sub(pattern, replacement, text, flags=flags)
                return (result,)
                
        except re.error as e:
            return (f"Error in regex pattern: {str(e)}\nOriginal text:\n{text}",)

NODE_CLASS_MAPPINGS = {
    "SimpleStringReplace": SimpleStringReplace,
    "RegexStringReplace": RegexStringReplace
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SimpleStringReplace": "Simple String Replace",
    "RegexStringReplace": "Regex String Replace"
}
