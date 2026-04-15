from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import logging
from pathlib import Path
from pydantic import BaseModel
from typing import List
import re
import io
import requests as http_requests
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

executor = ThreadPoolExecutor(max_workers=15)

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.tiff', '.heic', '.heif'}


# ── Models ──

class DriveLinkRequest(BaseModel):
    drive_link: str

class FolderItem(BaseModel):
    id: str
    name: str
    type: str
    path: str
    parent_folder: str = ""

class FolderStructureResponse(BaseModel):
    items: List[FolderItem]
    folder_name: str
    total_images: int
    total_folders: int


# ── Helpers ──

def extract_folder_id(drive_link: str) -> str:
    patterns = [
        r'folders/([a-zA-Z0-9-_]+)',
        r'id=([a-zA-Z0-9-_]+)',
        r'drive\.google\.com/drive/u/\d+/folders/([a-zA-Z0-9-_]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, drive_link)
        if match:
            return match.group(1)
    if re.match(r'^[a-zA-Z0-9-_]+$', drive_link.strip()):
        return drive_link.strip()
    raise ValueError("Invalid Drive link format.")


def is_image_file(name: str) -> bool:
    return any(name.lower().endswith(ext) for ext in IMAGE_EXTENSIONS)


def fetch_folder_entries(folder_id: str):
    url = f'https://drive.google.com/embeddedfolderview?id={folder_id}'
    resp = http_requests.get(url, timeout=15)
    if resp.status_code != 200:
        return [], "Unknown Folder"

    title_match = re.search(r'<title>(.*?)</title>', resp.text)
    folder_name = title_match.group(1) if title_match else "Drive Folder"

    entry_ids = re.findall(r'id="entry-([a-zA-Z0-9_-]+)"', resp.text)
    entry_titles = re.findall(r'<div class="flip-entry-title">(.*?)</div>', resp.text)

    return [{"id": eid, "name": etitle} for eid, etitle in zip(entry_ids, entry_titles)], folder_name


def classify_entries(entries, path_prefix, parent_folder):
    items = []
    subfolders = []
    for entry in entries:
        item_path = f"{path_prefix}/{entry['name']}" if path_prefix else entry['name']
        if is_image_file(entry['name']):
            items.append(FolderItem(id=entry["id"], name=entry["name"], type='image', path=item_path, parent_folder=parent_folder))
        else:
            items.append(FolderItem(id=entry["id"], name=entry["name"], type='folder', path=item_path, parent_folder=parent_folder))
            subfolders.append((entry["id"], entry["name"], item_path))
    return items, subfolders


def scan_folder(folder_id, path_prefix, parent_folder):
    entries, _ = fetch_folder_entries(folder_id)
    return classify_entries(entries, path_prefix, parent_folder)


def scan_level_parallel(queue):
    results = {}
    futures = {}

    for fid, _fname, fpath, *_ in queue:
        future = executor.submit(scan_folder, fid, fpath, fpath)
        futures[future] = fid

    for future in as_completed(futures):
        fid = futures[future]
        try:
            results[fid] = future.result()
        except:
            results[fid] = ([], [])

    return results


def fetch_all_recursive(folder_id):
    entries, folder_name = fetch_folder_entries(folder_id)

    items = []

    for entry in entries:
        if is_image_file(entry['name']):
            items.append(FolderItem(id=entry["id"], name=entry["name"], type='image', path=entry["name"], parent_folder=folder_name))
        else:
            items.append(FolderItem(id=entry["id"], name=entry["name"], type='folder', path=entry["name"], parent_folder=folder_name))

    return items, folder_name


# ── Routes ──

@api_router.get("/")
async def root():
    return {"message": "Google Drive Slideshow API"}


@api_router.post("/drive/folder")
async def get_folder_structure(request: DriveLinkRequest):
    try:
        folder_id = extract_folder_id(request.drive_link)

        items, folder_name = fetch_all_recursive(folder_id)

        if not items:
            raise HTTPException(status_code=400, detail="No content found. Make sure the folder is public.")

        total_images = sum(1 for i in items if i.type == 'image')
        total_folders = sum(1 for i in items if i.type == 'folder')

        return FolderStructureResponse(
            items=items,
            folder_name=folder_name,
            total_images=total_images,
            total_folders=total_folders
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@api_router.get("/drive/image/{file_id}")
async def get_drive_image(file_id: str):
    try:
        url = f'https://drive.google.com/uc?export=view&id={file_id}'
        resp = http_requests.get(url, timeout=15)

        if resp.status_code != 200:
            raise HTTPException(status_code=404, detail="Image not found")

        return StreamingResponse(
            io.BytesIO(resp.content),
            media_type='image/jpeg'
        )

    except:
        raise HTTPException(status_code=404, detail="Image not found")


# ── App setup ──

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
