"""
ComfyUI-Carneiro
Nodes: Random Image Loader, Cache Stats Monitor, Text Prompt Loader
"""

import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    from .random_image_loader import (
        NODE_CLASS_MAPPINGS as _RIL_CLASSES,
        NODE_DISPLAY_NAME_MAPPINGS as _RIL_NAMES,
    )
    from .carneiro_text_prompt_loader import (
        NODE_CLASS_MAPPINGS as _TPL_CLASSES,
        NODE_DISPLAY_NAME_MAPPINGS as _TPL_NAMES,
    )
    from . import carneiro_rename_api  # noqa: F401 – registers /carneiro/rename_images route
except ImportError:
    import random_image_loader as _ril
    import carneiro_text_prompt_loader as _tpl
    import carneiro_rename_api  # noqa: F401
    _RIL_CLASSES = _ril.NODE_CLASS_MAPPINGS
    _RIL_NAMES = _ril.NODE_DISPLAY_NAME_MAPPINGS
    _TPL_CLASSES = _tpl.NODE_CLASS_MAPPINGS
    _TPL_NAMES = _tpl.NODE_DISPLAY_NAME_MAPPINGS

NODE_CLASS_MAPPINGS = {**_RIL_CLASSES, **_TPL_CLASSES}
NODE_DISPLAY_NAME_MAPPINGS = {**_RIL_NAMES, **_TPL_NAMES}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']

WEB_DIRECTORY = "./web"
__version__ = "1.4.0"
