"""
Carneiro Rename & Resize API
Renames images in a folder with random 6-digit IDs and resizes any
image whose largest dimension exceeds max_dim.
Also handles resetting the tracking file for Carneiro Random Image.
"""

import asyncio
import os
import random
import uuid
from pathlib import Path

from aiohttp import web
from PIL import Image, ImageOps
from server import PromptServer

VALID_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.tiff', '.tif')
DEFAULT_MAX_DIM = 1024
TRACKING_FILE = ".carneiro_img_processed.json"


def _resize_image(path, max_dim):
    try:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)
            w, h = img.size
            if max(w, h) > max_dim:
                img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
                ext = os.path.splitext(path)[1].lower()
                if ext in ('.jpg', '.jpeg') and img.mode in ('RGBA', 'P', 'LA'):
                    img = img.convert('RGB')
                img.save(path, optimize=True, quality=90)
                return True
    except Exception as e:
        print(f"[Carneiro] Rename: falha ao redimensionar {os.path.basename(path)}: {e}")
    return False


def _process_images(directory, max_dim):
    files = [f for f in os.listdir(directory) if f.lower().endswith(VALID_EXTENSIONS)]
    if not files:
        return 0, 0

    count = len(files)
    ids = random.sample(range(100000, 1000000), min(count, 900000))

    # 1. Renomeação temporária com rollback em caso de falha
    temp_files = []
    try:
        for name in files:
            ext = os.path.splitext(name)[1]
            temp = f"temp_shuffle_{uuid.uuid4().hex}{ext}"
            os.rename(os.path.join(directory, name), os.path.join(directory, temp))
            temp_files.append((name, temp))
    except Exception as e:
        # Rollback dos temporários já renomeados
        for original, temp in temp_files:
            try:
                os.rename(os.path.join(directory, temp), os.path.join(directory, original))
            except Exception:
                pass
        raise RuntimeError(f"Falha na fase inicial de renomeação temporária: {e}")

    # 2. Renomeação final para os IDs e redimensionamento
    resized = 0
    errors = []
    for i, (orig_name, temp_name) in enumerate(temp_files):
        ext = os.path.splitext(temp_name)[1]
        final_name = f"{ids[i]}{ext}"
        final_path = os.path.join(directory, final_name)
        temp_path = os.path.join(directory, temp_name)
        try:
            os.rename(temp_path, final_path)
            if _resize_image(final_path, max_dim):
                resized += 1
        except Exception as e:
            errors.append(f"{temp_name} -> {final_name}: {e}")

    # Remove o tracking file antigo da pasta caso exista para reiniciar o ciclo limpo
    tracking_path = Path(directory) / TRACKING_FILE
    if tracking_path.exists():
        try:
            tracking_path.unlink()
        except Exception:
            pass

    if errors:
        print(f"[Carneiro] Rename concluiu com alguns erros: {errors}")

    print(f"[Carneiro] Rename: {count} renomeadas, {resized} redimensionadas (max {max_dim}px)")
    return count, resized


@PromptServer.instance.routes.post("/carneiro/rename_images")
async def rename_images(request):
    try:
        body = await request.json()
        folder = body.get("folder", "").strip()
        max_dim = int(body.get("max_dim", DEFAULT_MAX_DIM))

        if not folder:
            return web.json_response({"error": "Caminho da pasta vazio"}, status=400)
        if not os.path.isdir(folder):
            return web.json_response({"error": f"Diretorio nao encontrado: {folder}"}, status=400)

        # Executa em thread separada para não bloquear o event loop do ComfyUI
        loop = asyncio.get_event_loop()
        renamed, resized = await loop.run_in_executor(None, _process_images, folder, max_dim)

        return web.json_response({
            "renamed": renamed,
            "resized": resized,
            "max_dim": max_dim,
        })
    except Exception as e:
        print(f"[Carneiro] Rename API error: {e}")
        return web.json_response({"error": str(e)}, status=500)


@PromptServer.instance.routes.post("/carneiro/reset_tracker")
async def reset_tracker(request):
    try:
        body = await request.json()
        folder = body.get("folder", "").strip()

        if not folder:
            return web.json_response({"error": "Caminho da pasta vazio"}, status=400)
        if not os.path.isdir(folder):
            return web.json_response({"error": f"Diretorio nao encontrado: {folder}"}, status=400)

        tracking_path = Path(folder) / TRACKING_FILE
        if tracking_path.exists():
            tracking_path.unlink()
            message = "Rastreador resetado com sucesso."
        else:
            message = "Nenhum arquivo de rastreamento pendente encontrado."

        return web.json_response({"success": True, "message": message})
    except Exception as e:
        print(f"[Carneiro] Reset Tracker API error: {e}")
        return web.json_response({"error": str(e)}, status=500)
