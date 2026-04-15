from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
import os, io, re, requests as http_requests
from pydantic import BaseModel

app = FastAPI()

# Health check root
@app.get("/")
async def root():
    return {"message": "Server is running"}

api_router = APIRouter(prefix="/api")

@api_router.get("/")
async def api_root():
    return {"status": "API is active"}

API_KEY = os.getenv('GOOGLE_API_KEY')

class DriveLinkRequest(BaseModel):
    drive_link: str

def extract_folder_id(link: str) -> str:
    patterns = [r'folders/([a-zA-Z0-9-_]+)', r'id=([a-zA-Z0-9-_]+)']
    for p in patterns:
        match = re.search(p, link)
        if match: return match.group(1)
    return link.strip()

@api_router.post("/drive/folder")
async def get_folder_structure(request: DriveLinkRequest):
    try:
        folder_id = extract_folder_id(request.drive_link)
        # Google Drive API call to get files in the folder
        url = f"https://www.googleapis.com/drive/v3/files?q='{folder_id}'+in+parents&fields=files(id,name,mimeType)&key={API_KEY}"
        resp = http_requests.get(url)
        data = resp.json()
        
        if 'error' in data:
            raise HTTPException(status_code=400, detail=data['error']['message'])

        items = []
        # Dummy "All Photos" root for UI compatibility
        items.append({
            "id": "all_photos_root",
            "name": "All Photos",
            "type": "folder",
            "path": "All Photos"
        })

        for file in data.get('files', []):
            mime = file.get('mimeType', '').lower()
            name = file['name']
            
            # 1. Check if it's a folder
            if 'folder' in mime:
                items.append({
                    "id": file['id'],
                    "name": file['name'],
                    "type": "folder",
                    "path": file['name']
                })
            
            # 2. Check if it's an image (Case-insensitive check for extensions)
            elif 'image' in mime or any(name.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp', '.jfif', '.heic']):
                items.append({
                    "id": file['id'],
                    "name": file['name'],
                    "type": "image",
                    "path": f"All Photos/{file['name']}"
                })

        return {
            "items": items,
            "folder_name": "Drive Slideshow",
            "total_images": len([i for i in items if i['type'] == 'image']),
            "total_folders": len([i for i in items if i['type'] == 'folder'])
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@api_router.get("/drive/image/{file_id}")
async def get_drive_image(file_id: str):
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&key={API_KEY}"
    resp = http_requests.get(url, stream=True)
    return StreamingResponse(io.BytesIO(resp.content), media_type='image/jpeg')

app.include_router(api_router)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
