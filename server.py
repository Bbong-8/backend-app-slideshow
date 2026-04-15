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
        main_folder_id = extract_folder_id(request.drive_link)
        all_items = []
        
        # 1. Pehle saare sub-folders dhoondo jo main folder ke andar hain
        url = f"https://www.googleapis.com/drive/v3/files?q='{main_folder_id}'+in+parents+and+mimeType='application/vnd.google-apps.folder'+and+trashed=false&fields=files(id,name)&key={API_KEY}"
        folders_resp = http_requests.get(url).json()
        
        if 'error' in folders_resp:
            raise HTTPException(status_code=400, detail=folders_resp['error']['message'])

        # "All Photos" dummy folder for UI
        all_items.append({"id": "all_photos_root", "name": "All Photos", "type": "folder", "path": "All Photos"})

        # 2. Har folder ke andar ghuso aur images nikaalo
        for folder in folders_resp.get('files', []):
            folder_name = folder['name']
            all_items.append({"id": folder['id'], "name": folder_name, "type": "folder", "path": folder_name})
            
            # Sub-folder ki images dhoondo
            img_url = f"https://www.googleapis.com/drive/v3/files?q='{folder['id']}'+in+parents+and+trashed=false&fields=files(id,name,mimeType)&key={API_KEY}"
            imgs_resp = http_requests.get(img_url).json()
            
            for f in imgs_resp.get('files', []):
                mime = f.get('mimeType', '').lower()
                name = f['name'].lower()
                if 'image' in mime or any(name.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp', '.jfif']):
                    all_items.append({
                        "id": f['id'],
                        "name": f['name'],
                        "type": "image",
                        "path": f"{folder_name}/{f['name']}"
                    })

        # 3. Main root (agar wahan bhi kuch photos hain)
        root_img_url = f"https://www.googleapis.com/drive/v3/files?q='{main_folder_id}'+in+parents+and+mimeType!='application/vnd.google-apps.folder'+and+trashed=false&fields=files(id,name,mimeType)&key={API_KEY}"
        root_imgs = http_requests.get(root_img_url).json()
        for f in root_imgs.get('files', []):
            mime = f.get('mimeType', '').lower()
            name = f['name'].lower()
            if 'image' in mime or any(name.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                all_items.append({
                    "id": f['id'],
                    "name": f['name'],
                    "type": "image",
                    "path": f"All Photos/{f['name']}"
                })

        return {
            "items": all_items,
            "folder_name": "Drive Slideshow",
            "total_images": len([i for i in all_items if i['type'] == 'image']),
            "total_folders": len([i for i in all_items if i['type'] == 'folder'])
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
