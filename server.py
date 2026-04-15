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

# Render se API Key uthana
API_KEY = os.getenv('GOOGLE_API_KEY')

class DriveLinkRequest(BaseModel):
    drive_link: str

class FolderItem(BaseModel):
    id: str
    name: str
    type: str
    path: str

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
        # API Key use karke files fetch karna
        url = f"https://www.googleapis.com/drive/v3/files?q='{folder_id}'+in+parents&fields=files(id,name,mimeType)&key={API_KEY}"
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
    # API Key use karke image stream karna
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&key={API_KEY}"
    resp = http_requests.get(url)
    return StreamingResponse(io.BytesIO(resp.content), media_type='image/jpeg')

app.include_router(api_router)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
