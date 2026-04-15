from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
import os, io, re, requests as http_requests
from pydantic import BaseModel

app = FastAPI()

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
        # Scan everything inside the folder
        url = f"https://www.googleapis.com/drive/v3/files?q='{folder_id}'+in+parents&fields=files(id,name,mimeType)&key={API_KEY}"
        resp = http_requests.get(url)
        data = resp.json()
        
        if 'error' in data:
            raise HTTPException(status_code=400, detail=data['error']['message'])

        items = []
        for file in data.get('files', []):
            mime = file.get('mimeType', '').lower()
            
            if 'folder' in mime:
                item_type = 'folder'
                # Folder ka path uska naam hi rakho
                file_path = file['name']
            elif 'image/' in mime or any(ext in mime for ext in ['jpg', 'jpeg', 'png', 'webp']):
                item_type = 'image'
                # IMPORTANT: Emergent needs path as "folder_name/file_name"
                # Hum fake path bhejenge: "Main/filename" taki frontend ise Main folder mein dikhaye
                file_path = f"Main/{file['name']}"
            else:
                continue

            items.append({
                "id": file['id'],
                "name": file['name'],
                "type": item_type,
                "path": file_path
            })

        # Ek dummy "Main" folder add karo jisme saari images dikhein
        items.append({
            "id": "root_dummy",
            "name": "Main",
            "type": "folder",
            "path": "Main"
        })

        return {
            "items": items,
            "folder_name": "Google Drive",
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
