"""Category colours shared by the app and the HTML report (Apple system colours).

Each entry is (light mode, dark mode).
"""

CATEGORY_COLOURS = {
    "cpu": ("#007aff", "#0a84ff"),
    "gpu": ("#af52de", "#bf5af2"),
    "memory": ("#28a745", "#30d158"),
    "storage": ("#f08c00", "#ff9f0a"),
    "neural": ("#ff2d55", "#ff375f"),
    "sustained": ("#1a9fd6", "#64d2ff"),
}


def colour(key: str, dark: bool) -> str:
    light_hex, dark_hex = CATEGORY_COLOURS.get(key, ("#8e8e93", "#98989d"))
    return dark_hex if dark else light_hex
