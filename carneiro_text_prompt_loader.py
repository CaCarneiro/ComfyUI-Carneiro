"""
CarneiroTextPromptLoader Node for ComfyUI
==========================================
Loads text prompts from .txt files with sequential processing and auto-cleanup.

Author: Carneiro
Version: 1.1.0
Date: 2026-02-26

Features:
- Random or sequential .txt file selection
- Content output as STRING
- Processed files tracking
- Auto-delete processed files (optional)
- Smart caching with validation
- Automatic reset when folder empties
- Subfolder scanning support (optional)
"""

import os
import random
import time
import json
from pathlib import Path
from typing import Tuple, List, Optional

class CarneiroTextPromptLoader:
    """
    ComfyUI node for loading text prompts from .txt files.
    
    Workflow:
    1. Scans folder (and optionally subfolders) for .txt files
    2. Loads random/sequential unprocessed file
    3. Returns content as string
    4. Optionally deletes processed file
    5. Tracks processed files to avoid repetition
    """
    
    # ==================== ComfyUI Node Configuration ====================
    
    @classmethod
    def INPUT_TYPES(cls):
        """Define input parameters for ComfyUI interface."""
        return {
            "required": {
                "folder_path": ("STRING", {
                    "default": "/path/to/prompts",
                    "multiline": False,
                    "placeholder": "Path to folder containing .txt files"
                }),
                "mode": (["random", "sequential"], {
                    "default": "random"
                }),
                "delete_after_use": ("BOOLEAN", {
                    "default": False,
                    "label_on": "Delete file",
                    "label_off": "Keep file"
                }),
                "encoding": (["utf-8", "latin-1", "ascii", "cp1252"], {
                    "default": "utf-8"
                }),
                "force_rescan": ("BOOLEAN", {
                    "default": False,
                    "label_on": "Force rescan",
                    "label_off": "Use cache"
                }),
                "include_subfolders": ("BOOLEAN", {
                    "default": False,
                    "label_on": "Include subfolders",
                    "label_off": "Root folder only"
                }),
            },
            "optional": {
                "seed": ("INT", {
                    "default": -1,
                    "min": -1,
                    "max": 0xffffffffffffffff,
                    "tooltip": "Seed for random selection (-1 = random)"
                }),
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING", "INT", "INT")
    RETURN_NAMES = ("prompt_text", "filename", "total_files", "processed_count")
    FUNCTION = "load_prompt"
    CATEGORY = "🐦 Carneiro Nodes/Text"
    OUTPUT_NODE = False
    
    DESCRIPTION = """
    Loads text prompts from .txt files with intelligent management.
    
    **Modes:**
    - Random: Selects unprocessed file randomly
    - Sequential: Processes files in alphabetical order
    
    **Features:**
    - Tracks processed files automatically
    - Optional subfolder scanning (relative paths preserved)
    - Optional auto-delete after use
    - Resets when all files processed
    - UTF-8 encoding support (configurable)
    """
    
    # ==================== Class Variables ====================
    
    # Cache key format: "{folder_path}::{subfolders}"
    _cache = {}  # {cache_key: {"files": [...], "mtime": float}}
    _cache_ttl = 600  # 10 minutes
    _tracking_file = ".carneiro_processed.json"
    
    # ==================== Core Methods ====================
    
    def __init__(self):
        """Initialize node instance."""
        self.last_loaded_file = None
        self.current_folder = None
    
    def load_prompt(
        self,
        folder_path: str,
        mode: str = "random",
        include_subfolders: bool = False,
        delete_after_use: bool = False,
        encoding: str = "utf-8",
        force_rescan: bool = False,
        seed: int = -1
    ) -> Tuple[str, str, int, int]:
        """
        Main execution function.
        
        Args:
            folder_path: Path to folder containing .txt files
            mode: Selection mode ("random" or "sequential")
            include_subfolders: Whether to scan subfolders recursively
            delete_after_use: Whether to delete file after loading
            encoding: Text encoding (utf-8, latin-1, ascii, cp1252)
            force_rescan: Force cache refresh
            seed: Random seed (-1 for true random)
        
        Returns:
            Tuple of (prompt_text, filename, total_files, processed_count)
        
        Raises:
            ValueError: If folder is empty or invalid
            FileNotFoundError: If folder doesn't exist
        """
        # Validate folder
        folder_path = self._normalize_path(folder_path)
        if not os.path.isdir(folder_path):
            raise FileNotFoundError(f"Folder not found: {folder_path}")
        
        self.current_folder = folder_path
        
        # Get available .txt files
        # Files are stored as relative paths to folder_path (e.g. "sub/file.txt")
        txt_files = self._get_txt_files(folder_path, force_rescan, include_subfolders)
        if not txt_files:
            raise ValueError(
                f"No .txt files found in {folder_path}"
                + (" (including subfolders)" if include_subfolders else "")
            )
        
        # Load tracking data
        processed_files = self._load_tracking(folder_path)
        
        # Get unprocessed files
        unprocessed = [f for f in txt_files if f not in processed_files]
        
        # Reset if all files processed
        if not unprocessed:
            print(f"[Carneiro] All {len(txt_files)} files processed. Resetting tracker.")
            processed_files.clear()
            self._save_tracking(folder_path, processed_files)
            unprocessed = txt_files.copy()
        
        # Select file based on mode
        if mode == "sequential":
            # Sort by relative path (alphabetical, subfolders included naturally)
            selected_file = sorted(unprocessed)[0]
        else:  # random
            if seed >= 0:
                random.seed(seed)
            selected_file = random.choice(unprocessed)
        
        # Build full path (works for both "file.txt" and "sub/file.txt")
        file_path = os.path.join(folder_path, selected_file)
        
        # Read file content
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read().strip()
        except UnicodeDecodeError:
            # Fallback to different encoding
            print(f"[Carneiro] Failed to read with {encoding}, trying latin-1")
            with open(file_path, 'r', encoding='latin-1') as f:
                content = f.read().strip()
        
        # Mark as processed
        processed_files.add(selected_file)
        self._save_tracking(folder_path, processed_files)
        
        # Store reference
        self.last_loaded_file = file_path
        
        # Delete file if requested
        if delete_after_use:
            try:
                os.remove(file_path)
                print(f"[Carneiro] Deleted: {selected_file}")
                # Update cache
                cache_key = self._cache_key(folder_path, include_subfolders)
                if cache_key in self._cache:
                    try:
                        self._cache[cache_key]["files"].remove(selected_file)
                    except ValueError:
                        pass
            except Exception as e:
                print(f"[Carneiro] Failed to delete {selected_file}: {e}")
        
        # Prepare outputs
        total_files = len(txt_files)
        processed_count = len(processed_files)
        
        print(f"[Carneiro] Loaded: {selected_file} ({processed_count}/{total_files} processed)")
        
        return (content, selected_file, total_files, processed_count)
    
    # ==================== Helper Methods ====================
    
    def _normalize_path(self, path: str) -> str:
        """Normalize and expand path."""
        return os.path.abspath(os.path.expanduser(path))
    
    def _cache_key(self, folder_path: str, include_subfolders: bool) -> str:
        """Build a cache key that accounts for the subfolder flag."""
        return f"{folder_path}::{'recursive' if include_subfolders else 'flat'}"
    
    def _scan_files_flat(self, folder_path: str) -> List[str]:
        """Return .txt filenames in the root folder only."""
        return [
            f for f in os.listdir(folder_path)
            if f.lower().endswith('.txt') and
            os.path.isfile(os.path.join(folder_path, f))
        ]
    
    def _scan_files_recursive(self, folder_path: str) -> List[str]:
        """
        Return .txt files from root folder AND all subfolders.
        Paths are relative to folder_path (e.g. "subfolder/prompt.txt").
        Skips hidden directories (names starting with '.').
        """
        relative_paths = []
        for root, dirs, files in os.walk(folder_path):
            # Skip hidden directories in-place to avoid descending into them
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for filename in files:
                if filename.lower().endswith('.txt'):
                    abs_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(abs_path, folder_path)
                    # Normalise separators to forward slashes for consistency
                    rel_path = rel_path.replace(os.sep, '/')
                    relative_paths.append(rel_path)
        return relative_paths
    
    def _get_txt_files(
        self,
        folder_path: str,
        force_rescan: bool,
        include_subfolders: bool
    ) -> List[str]:
        """
        Get list of .txt files with caching.
        
        Args:
            folder_path: Folder to scan
            force_rescan: Bypass cache
            include_subfolders: Whether to scan recursively
        
        Returns:
            List of relative .txt paths (just filename when flat,
            "subfolder/filename" when recursive)
        """
        current_time = time.time()
        cache_key = self._cache_key(folder_path, include_subfolders)
        
        # Check cache validity
        if (not force_rescan and
                cache_key in self._cache and
                current_time - self._cache[cache_key]["mtime"] < self._cache_ttl):
            
            cached_files = set(self._cache[cache_key]["files"])
            
            # Quick validation against current disk state
            if include_subfolders:
                actual_files = set(self._scan_files_recursive(folder_path))
            else:
                actual_files = set(self._scan_files_flat(folder_path))
            
            if cached_files == actual_files:
                print(f"[Carneiro] Cache hit: {len(cached_files)} files")
                return list(cached_files)
        
        # Scan folder
        mode_label = "recursively" if include_subfolders else "flat"
        print(f"[Carneiro] Scanning folder ({mode_label}): {folder_path}")
        
        if include_subfolders:
            txt_files = self._scan_files_recursive(folder_path)
        else:
            txt_files = self._scan_files_flat(folder_path)
        
        # Update cache
        self._cache[cache_key] = {
            "files": txt_files,
            "mtime": current_time,
        }
        
        print(f"[Carneiro] Found {len(txt_files)} .txt files")
        return txt_files
    
    def _load_tracking(self, folder_path: str) -> set:
        """
        Load processed files tracking data.
        
        Args:
            folder_path: Folder containing tracking file
        
        Returns:
            Set of processed relative filenames/paths
        """
        tracking_path = os.path.join(folder_path, self._tracking_file)
        
        if os.path.exists(tracking_path):
            try:
                with open(tracking_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return set(data.get("processed", []))
            except Exception as e:
                print(f"[Carneiro] Failed to load tracking: {e}")
                return set()
        
        return set()
    
    def _save_tracking(self, folder_path: str, processed_files: set) -> None:
        """
        Save processed files tracking data.
        
        Args:
            folder_path: Folder to save tracking file
            processed_files: Set of processed relative filenames/paths
        """
        tracking_path = os.path.join(folder_path, self._tracking_file)
        
        try:
            with open(tracking_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "processed": list(processed_files),
                    "last_updated": time.time()
                }, f, indent=2)
        except Exception as e:
            print(f"[Carneiro] Failed to save tracking: {e}")
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        """
        ComfyUI cache invalidation.
        Returns unique value to force re-execution when needed.
        """
        # Always re-execute if force_rescan or delete_after_use
        if kwargs.get("force_rescan", False) or kwargs.get("delete_after_use", False):
            return float("nan")
        
        # Otherwise use timestamp + seed
        seed = kwargs.get("seed", -1)
        if seed < 0:
            return time.time()
        return f"{seed}_{time.time()}"


# ==================== ComfyUI Node Registration ====================

NODE_CLASS_MAPPINGS = {
    "CarneiroTextPromptLoader": CarneiroTextPromptLoader
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "CarneiroTextPromptLoader": "🐦 Text Prompt Loader"
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
