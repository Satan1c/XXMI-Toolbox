import os

# "bl_ext.<repository>.xxmi_toolbox" as an extension, "xxmi_toolbox" as a legacy add-on.
ADDON = __package__.rpartition(".")[0]
ADDON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IS_EXTENSION = ADDON.startswith("bl_ext.")
