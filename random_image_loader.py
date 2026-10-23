"""
ComfyUI-Carneiro - Random Image Loader
VERSAO 2.0 - Rastreamento, modo sequencial e auto-delete

Custom Node para selecao de imagens com:
- Modos: aleatorio ou sequencial
- Rastreamento de arquivos processados (evita repeticao)
- Auto-reset quando todos os arquivos sao processados
- Delete automatico apos uso (opcional)
- Cache LRU inteligente
- Entropia real do OS para aleatoriedade
- Gestao otimizada para grandes colecoes
"""

import os
import json
import random
import time
import hashlib
from pathlib import Path
from typing import Tuple, Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import OrderedDict

import numpy as np
import torch
import folder_paths
from PIL import Image, ImageOps


class LRUCache:
    """Cache LRU com limite de tamanho e expiracao automatica"""

    def __init__(self, max_size: int = 50, ttl: timedelta = timedelta(minutes=10)):
        self.cache: OrderedDict = OrderedDict()
        self.max_size = max_size
        self.ttl = ttl
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Dict]:
        if key not in self.cache:
            self._misses += 1
            return None

        entry = self.cache[key]
        if datetime.now() - entry['timestamp'] > self.ttl:
            del self.cache[key]
            self._misses += 1
            return None

        self.cache.move_to_end(key)
        self._hits += 1
        return entry

    def set(self, key: str, value: Dict) -> None:
        if key in self.cache:
            del self.cache[key]
        self.cache[key] = value
        if len(self.cache) > self.max_size:
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]

    def clear(self) -> None:
        self.cache.clear()
        self._hits = 0
        self._misses = 0

    def stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'hits': self._hits,
            'misses': self._misses,
            'hit_rate': f"{hit_rate:.1f}%",
            'total_requests': total,
        }


class RandomImageLoader:
    """
    Carrega imagem com rastreamento inteligente e cache otimizado.

    Modos:
    - random: seleciona aleatoriamente entre imagens nao processadas
    - sequential: processa em ordem alfabetica

    Funcionalidades:
    - Rastreia arquivos ja processados via .carneiro_img_processed.json
    - Auto-reset quando todos os arquivos forem processados
    - Delete automatico apos uso (opcional)
    - Cache LRU compartilhado entre instancias
    - Seed reproduzivel ou entropia real do OS
    - Suporte a grandes colecoes (ate 50k arquivos)
    """

    _file_cache = LRUCache(max_size=50, ttl=timedelta(minutes=10))
    _execution_counter = 0

    MAX_FILES_PER_SCAN = 50000

    IMAGE_EXTENSIONS = {
        '.png', '.jpg', '.jpeg', '.webp', '.bmp',
        '.gif', '.tiff', '.tif',
    }

    _tracking_file = ".carneiro_img_processed.json"

    def __init__(self):
        self.type = "RandomImageLoader"
        self.output_node = False
        self._rng = random.Random()

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        input_dir = folder_paths.get_input_directory()
        input_images = [""] + sorted(
            entry.name for entry in Path(input_dir).iterdir()
            if entry.is_file() and entry.suffix.lower() in cls.IMAGE_EXTENSIONS
        )

        return {
            "required": {
                "folder_path": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "Caminho da pasta de imagens",
                }),
                "mode": (["random", "sequential"], {
                    "default": "random",
                }),
                "delete_after_use": ("BOOLEAN", {
                    "default": False,
                    "label_on": "Deletar arquivo",
                    "label_off": "Manter arquivo",
                }),
                "force_rescan": ("BOOLEAN", {
                    "default": False,
                    "label_on": "Forcar rescan",
                    "label_off": "Usar cache",
                }),
                "include_subfolders": ("BOOLEAN", {
                    "default": False,
                    "label_on": "Incluir subpastas",
                    "label_off": "Apenas raiz",
                }),
            },
            "optional": {
                "seed": ("INT", {
                    "default": -1,
                    "min": -1,
                    "max": 0xffffffffffffffff,
                    "step": 1,
                    "display": "number",
                    "tooltip": "Seed para selecao aleatoria (-1 = aleatorio real)",
                }),
                "manual_image": ("BOOLEAN", {
                    "default": False,
                    "label_on": "Carregamento manual",
                    "label_off": "Carregamento aleatorio",
                }),
                "image": (input_images, {
                    "image_upload": True,
                    "tooltip": "Usada somente com carregamento manual ativado.",
                }),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "INT", "INT")
    RETURN_NAMES = ("image", "image_path", "filename", "total_files", "processed_count")
    FUNCTION = "execute"
    CATEGORY = "image/loaders"

    def execute(
        self,
        folder_path: str,
        mode: str = "random",
        delete_after_use: bool = False,
        force_rescan: bool = False,
        include_subfolders: bool = False,
        seed: int = -1,
        manual_image: bool = False,
        image: str = "",
    ) -> Tuple[torch.Tensor, str, str, int, int]:
        """
        Seleciona imagem com rastreamento de processados.

        Returns:
            Tuple (tensor_imagem, caminho_completo, nome_arquivo, total_arquivos, processados)
        """

        RandomImageLoader._execution_counter += 1

        if manual_image:
            if not image:
                raise ValueError("Selecione uma imagem para o carregamento manual")
            if not folder_paths.exists_annotated_filepath(image):
                raise ValueError(f"Imagem invalida: {image}")

            image_path = Path(folder_paths.get_annotated_filepath(image))
            image_tensor = self._load_image(image_path)
            print(f"[Carneiro] Carregado manualmente: {image_path.name}")
            return (image_tensor, str(image_path), image_path.name, 1, 0)

        # Validacao do caminho
        folder_path = folder_path.strip()
        if not folder_path:
            raise ValueError("Caminho da pasta nao pode ser vazio")

        path_obj = Path(folder_path).expanduser().resolve()
        if not path_obj.exists():
            raise ValueError(f"Caminho nao existe: {path_obj}")
        if not path_obj.is_dir():
            raise ValueError(f"Nao e um diretorio: {path_obj}")

        # Obter lista de arquivos (caminhos relativos)
        image_files = self._get_image_files(path_obj, include_subfolders, force_rescan)
        if not image_files:
            raise ValueError(
                f"Nenhuma imagem encontrada em: {path_obj}"
                + (" (incluindo subpastas)" if include_subfolders else "")
            )

        # Rastreamento de processados
        processed = self._load_tracking(path_obj)
        unprocessed = [f for f in image_files if f not in processed]

        if not unprocessed:
            print(f"[Carneiro] Todas as {len(image_files)} imagens processadas. Resetando rastreador.")
            processed.clear()
            self._save_tracking(path_obj, processed)
            unprocessed = list(image_files)

        # Selecao por modo
        if mode == "sequential":
            selected_rel = sorted(unprocessed)[0]
        else:
            self._configure_seed(seed)
            selected_rel = self._rng.choice(unprocessed)

        selected_path = path_obj / selected_rel

        # Marcar como processado
        processed.add(selected_rel)
        self._save_tracking(path_obj, processed)

        image_tensor = self._load_image(selected_path)

        # Delete apos uso
        if delete_after_use:
            try:
                selected_path.unlink()
                print(f"[Carneiro] Deletado: {selected_rel}")
                self._remove_from_cache(path_obj, include_subfolders, selected_rel)
            except Exception as e:
                print(f"[Carneiro] Falha ao deletar {selected_rel}: {e}")

        total = len(image_files)
        processed_count = len(processed)
        print(f"[Carneiro] Carregado: {selected_rel} ({processed_count}/{total} processados)")

        return (image_tensor, str(selected_path), selected_path.name, total, processed_count)

    def _load_image(self, image_path: Path) -> torch.Tensor:
        with Image.open(image_path) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode != "RGB":
                img = img.convert("RGB")
            img_array = np.array(img).astype(np.float32) / 255.0
        return torch.from_numpy(img_array).unsqueeze(0)

    # ── Cache de arquivos ────────────────────────────────────────────────────

    def _get_image_files(
        self, path: Path, recursive: bool, force_rescan: bool
    ) -> List[str]:
        """Retorna lista de caminhos relativos (str) com cache LRU."""
        cache_key = self._generate_cache_key(path, recursive)

        if not force_rescan:
            cached = self._file_cache.get(cache_key)
            if cached and self._is_cache_valid(cached, path):
                return cached['files']

        files = self._scan_directory(path, recursive)
        self._file_cache.set(cache_key, {
            'files': files,
            'timestamp': datetime.now(),
            'folder_mtime': path.stat().st_mtime,
            'count': len(files),
        })
        return files

    def _scan_directory(self, path: Path, recursive: bool) -> List[str]:
        """Escaneia o diretorio, retornando caminhos relativos."""
        results = []
        iterator = path.rglob("*") if recursive else path.glob("*")
        for file_path in iterator:
            if len(results) >= self.MAX_FILES_PER_SCAN:
                print(f"[Carneiro] Limite de {self.MAX_FILES_PER_SCAN} arquivos atingido")
                break
            try:
                if not file_path.is_file():
                    continue
                if file_path.name.startswith('.'):
                    continue
                if file_path.suffix.lower() in self.IMAGE_EXTENSIONS:
                    results.append(file_path.relative_to(path).as_posix())
            except (OSError, PermissionError):
                continue
        return results

    def _generate_cache_key(self, path: Path, recursive: bool) -> str:
        return f"{path}|{recursive}"

    def _is_cache_valid(self, cached_entry: Dict, path: Path) -> bool:
        try:
            return path.stat().st_mtime <= cached_entry['folder_mtime']
        except OSError:
            return False

    def _remove_from_cache(self, path: Path, recursive: bool, rel_path: str) -> None:
        """Remove arquivo deletado da entrada de cache correspondente."""
        cache_key = self._generate_cache_key(path, recursive)
        cached = self._file_cache.get(cache_key)
        if cached:
            try:
                cached['files'].remove(rel_path)
            except ValueError:
                pass

    # ── Rastreamento de processados ──────────────────────────────────────────

    def _load_tracking(self, folder: Path) -> set:
        tracking_path = folder / self._tracking_file
        if tracking_path.exists():
            try:
                with open(tracking_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return set(data.get("processed", []))
            except Exception as e:
                print(f"[Carneiro] Falha ao carregar rastreamento: {e}")
        return set()

    def _save_tracking(self, folder: Path, processed: set) -> None:
        tracking_path = folder / self._tracking_file
        try:
            with open(tracking_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "processed": list(processed),
                    "last_updated": time.time(),
                }, f, indent=2)
        except Exception as e:
            print(f"[Carneiro] Falha ao salvar rastreamento: {e}")

    # ── Seed ────────────────────────────────────────────────────────────────

    def _configure_seed(self, seed: int) -> None:
        if seed == -1:
            self._rng.seed(int.from_bytes(os.urandom(8), byteorder='big'))
        else:
            self._rng.seed(seed)

    # ── ComfyUI hooks ────────────────────────────────────────────────────────

    @classmethod
    def IS_CHANGED(cls, **kwargs) -> Any:
        image = kwargs.get('image', '')
        if kwargs.get('manual_image', False) and image:
            image_path = folder_paths.get_annotated_filepath(image)
            image_hash = hashlib.sha256()
            with open(image_path, 'rb') as image_file:
                image_hash.update(image_file.read())
            return image_hash.hexdigest()

        if kwargs.get('manual_image', False):
            return float("nan")

        if kwargs.get('delete_after_use', False) or kwargs.get('force_rescan', False):
            return float("nan")

        seed = kwargs.get('seed', -1)
        if seed == -1:
            return time.time() + random.random()
        return float(seed)

    @classmethod
    def get_cache_stats(cls) -> Dict[str, Any]:
        return cls._file_cache.stats()


class CacheStatsMonitor:
    """Node opcional para visualizar estatisticas do cache"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "trigger": ("*", {}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("stats",)
    FUNCTION = "execute"
    CATEGORY = "utils/debug"
    OUTPUT_NODE = True

    def execute(self, trigger=None):
        stats = RandomImageLoader.get_cache_stats()

        stats_text = (
            f"CARNEIRO IMAGE LOADER STATS:\n\n"
            f"CACHE:\n"
            f"  Size: {stats['size']}/{stats['max_size']} entries\n"
            f"  Hits: {stats['hits']}\n"
            f"  Misses: {stats['misses']}\n"
            f"  Hit Rate: {stats['hit_rate']}\n\n"
            f"TOTAL EXECUTIONS: {RandomImageLoader._execution_counter}"
        )
        print(stats_text)
        return (stats_text,)


# ============================================================================
# REGISTRO DOS NODES NO COMFYUI
# ============================================================================

NODE_CLASS_MAPPINGS = {
    "CarneiroRandomImageLoader": RandomImageLoader,
    "CarneiroCacheStats": CacheStatsMonitor,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "CarneiroRandomImageLoader": "Carneiro Random Image",
    "CarneiroCacheStats": "Carneiro Cache Stats",
}
