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

# Render ke environment variable se API Key uthana
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
        # Google API se files list karna
        url = f"https://www.googleapis.com/drive/v3/files?q='{folder_id}'+in+parents&fields=files(id,name,mimeType)&key={API_KEY}"
        resp = http_requests.get(url)
        data = resp.json()
        
        if 'error' in data:
            raise HTTPException(status_code=400, detail=data['error']['message'])

        items = []
        for file in data.get('files', []):
            mime_type = file.get('mimeType', '')
            # Folder aur Images ko sahi se classify karna
            is_folder = mime_type == 'application/vnd.google-apps.folder'
            is_image = 'image/' in mime_type
            
            if is_folder:
                item_type = 'folder'
            elif is_image:
                item_type = 'image'
            else:
                continue # Agar file image ya folder nahi hai toh skip karo

            items.append(FolderItem(
                id=file['id'],
                name=file['name'],
                type=item_type,
                path=file['name']
            ))

        return {"items": items, "folder_name": "Drive Folder", "total_images": len([i for i in items if i.type == 'image']), "total_folders": len([i for i in items if i.type == 'folder'])}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@api_router.get("/drive/image/{file_id}")
async def get_drive_image(file_id: str):
    # Image download proxy with API Key
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&key={API_KEY}"
    resp = http_requests.get(url, stream=True)
    
    if resp.status_code != 200:
        raise HTTPException(status_code=404, detail="Google API se photo nahi mili")

    return StreamingResponse(io.BytesIO(resp.content), media_type='image/jpeg')

app.include_router(api_router)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
