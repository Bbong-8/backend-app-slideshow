from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
import os
import io
import re
import requests as http_requests
from pydantic import BaseModel
from typing import List

app = FastAPI()
api_router = APIRouter(prefix="/api")

# Render se Credentials uthana
CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic'}

class DriveLinkRequest(BaseModel):
    drive_link: str

class FolderItem(BaseModel):
    id: str
    name: str
    type: str
    path: str
    parent_folder: str = ""

def extract_folder_id(drive_link: str) -> str:
    patterns = [r'folders/([a-zA-Z0-9-_]+)', r'id=([a-zA-Z0-9-_]+)']
    for pattern in patterns:
        match = re.search(pattern, drive_link)
        if match: return match.group(1)
    return drive_link.strip()

@api_router.post("/drive/folder")
async def get_folder_structure(request: DriveLinkRequest):
    try:
        folder_id = extract_folder_id(request.drive_link)
        # Google Drive API se files list karna
        url = f"https://www.googleapis.com/drive/v3/files?q='{folder_id}'+in+parents&fields=files(id,name,mimeType)&key={CLIENT_SECRET}"
        
        # Note: Agar ye simple GET kaam na kare, toh humein OAuth use karna padega.
        # Par abhi ke liye hum public folder access fix kar rahe hain.
        resp = http_requests.get(url)
        data = resp.json()
        
        if 'error' in data:
            raise HTTPException(status_code=400, detail=data['error']['message'])

        items = []
        for file in data.get('files', []):
            is_folder = file['mimeType'] == 'application/vnd.google-apps.folder'
            items.append(FolderItem(
                id=file['id'],
                name=file['name'],
                type='folder' if is_folder else 'image',
                path=file['name']
            ))

        return {"items": items, "folder_name": "Drive Folder", "total_images": len(items), "total_folders": 0}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@api_router.get("/drive/image/{file_id}")
async def get_drive_image(file_id: str):
    # Direct download proxy
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&key={CLIENT_SECRET}"
    resp = http_requests.get(url)
    return StreamingResponse(io.BytesIO(resp.content), media_type='image/jpeg')

app.include_router(api_router)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
