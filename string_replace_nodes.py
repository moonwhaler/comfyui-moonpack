import re

CATEGORY = "MoonPack/string"

HELP_TEXT = """Find/replace pairs (one per line, separated by =>):
hello => hi
world => earth
old => new

Empty replacement removes text:
remove_this =>

Lines without '=>' are reported via the 'ignored_lines' output.
Replacements are applied sequentially: if 'A => B' and 'B => C' are
both defined, 'A' becomes 'C'."""

REGEX_HELP = """Common patterns:
.       any character
.*      any characters (greedy)
\\d      digit
\\w      word character
[abc]   character class
(text)  capture group  (\\1, \\2, … in replacement)
"""


class SimpleStringReplace:
    DESCRIPTION = (
        "Sequential find/replace using 'find => replace' lines. "
        "Optional whole-word matching. Malformed lines are reported, not silently dropped."
    )
    SEARCH_ALIASES = ["replace", "substitute", "find replace", "string"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"forceInput": True, "tooltip": "Source text."}),
                "find_replace_pairs": ("STRING", {
                    "multiline": True,
                    "default": "find => replace\nold => new",
                    "placeholder": HELP_TEXT,
                    "tooltip": "One pair per line in 'find => replace' format. Empty replacement removes text.",
                }),
            },
            "optional": {
                "whole_word_match": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "If true, only complete words match (uses regex \\b boundaries).",
                }),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("text", "ignored_lines")
    FUNCTION = "replace"
    CATEGORY = CATEGORY

    def replace(self, text, find_replace_pairs, whole_word_match=False):
        if not text:
            return (text, "")
        result = text
        ignored = []
        for raw in find_replace_pairs.split("\n"):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=>" not in line:
                ignored.append(line)
                continue
            find, repl = line.split("=>", 1)
            find = find.strip()
            repl = repl.strip()
            if not find:
                ignored.append(line)
                continue
            if whole_word_match:
                result = re.sub(r"\b" + re.escape(find) + r"\b", repl, result)
            else:
                result = result.replace(find, repl)
        return (result, "\n".join(ignored))


class RegexStringReplace:
    DESCRIPTION = (
        "Regex find/replace with case-insensitive, multiline, and dotall flags. "
        "Supports a non-destructive test_mode that highlights matches with >>>...<<<."
    )
    SEARCH_ALIASES = ["regex", "regexp", "replace", "substitute"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"forceInput": True, "tooltip": "Source text."}),
                "pattern": ("STRING", {
                    "multiline": True,
                    "placeholder": REGEX_HELP,
                    "tooltip": "Python regex pattern.",
                }),
                "replacement": ("STRING", {
                    "multiline": True,
                    "tooltip": "Replacement string. Use \\1, \\2, … for capture groups.",
                }),
            },
            "optional": {
                "case_insensitive": ("BOOLEAN", {"default": False, "tooltip": "Apply re.IGNORECASE."}),
                "multiline":        ("BOOLEAN", {"default": False, "tooltip": "Apply re.MULTILINE (^/$ match line boundaries)."}),
                "dotall":           ("BOOLEAN", {"default": False, "tooltip": "Apply re.DOTALL (. matches newlines)."}),
                "test_mode":        ("BOOLEAN", {"default": False, "tooltip": "Highlight matches with >>>…<<< instead of replacing."}),
            },
        }

    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("text", "match_count")
    FUNCTION = "replace"
    CATEGORY = CATEGORY

    def replace(self, text, pattern, replacement, case_insensitive=False,
                multiline=False, dotall=False, test_mode=False):
        if not text or not pattern:
            return (text, 0)
        flags = 0
        if case_insensitive: flags |= re.IGNORECASE
        if multiline:        flags |= re.MULTILINE
        if dotall:           flags |= re.DOTALL
        try:
            matches = list(re.finditer(pattern, text, flags=flags))
            count = len(matches)
            if test_mode:
                result = text
                for m in reversed(matches):
                    s, e = m.span()
                    result = f"{result[:s]}>>>{result[s:e]}<<<{result[e:]}"
                return (result, count)
            return (re.sub(pattern, replacement, text, flags=flags), count)
        except re.error as e:
            return (f"<regex error: {e}>\n{text}", 0)


class RegexExtract:
    DESCRIPTION = (
        "Extracts the first or all regex matches from text. "
        "If the pattern has a capture group, returns the group; otherwise the whole match."
    )
    SEARCH_ALIASES = ["regex", "extract", "capture", "find", "search"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"forceInput": True, "tooltip": "Source text."}),
                "pattern": ("STRING", {
                    "multiline": True,
                    "placeholder": REGEX_HELP,
                    "tooltip": "Regex pattern. Use a capture group to extract a substring.",
                }),
            },
            "optional": {
                "case_insensitive": ("BOOLEAN", {"default": False}),
                "multiline":        ("BOOLEAN", {"default": False}),
                "dotall":           ("BOOLEAN", {"default": False}),
                "all_matches": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "If true, every match is emitted as a separate item (OUTPUT_IS_LIST).",
                }),
                "default": ("STRING", {
                    "default": "",
                    "tooltip": "Returned when there is no match.",
                }),
            },
        }

    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("match", "count")
    OUTPUT_IS_LIST = (True, False)
    FUNCTION = "extract"
    CATEGORY = CATEGORY

    def extract(self, text, pattern, case_insensitive=False, multiline=False,
                dotall=False, all_matches=False, default=""):
        if not text or not pattern:
            return ([default], 0)
        flags = 0
        if case_insensitive: flags |= re.IGNORECASE
        if multiline:        flags |= re.MULTILINE
        if dotall:           flags |= re.DOTALL
        try:
            matches = list(re.finditer(pattern, text, flags=flags))
        except re.error as e:
            return ([f"<regex error: {e}>"], 0)
        if not matches:
            return ([default], 0)

        def _pick(m):
            return m.group(1) if m.groups() else m.group(0)

        if all_matches:
            return ([_pick(m) for m in matches], len(matches))
        return ([_pick(matches[0])], 1)


NODE_CLASS_MAPPINGS = {
    "MoonPack_SimpleStringReplace": SimpleStringReplace,
    "MoonPack_RegexStringReplace": RegexStringReplace,
    "MoonPack_RegexExtract": RegexExtract,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MoonPack_SimpleStringReplace": "Simple String Replace",
    "MoonPack_RegexStringReplace": "Regex String Replace",
    "MoonPack_RegexExtract": "Regex Extract",
}
