from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
import os, io, re, requests as http_requests
from pydantic import BaseModel
from PIL import Image  # Compression ke liye

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Server is running with Compression Engine"}

api_router = APIRouter(prefix="/api")

API_KEY = os.getenv('GOOGLE_API_KEY')

class DriveLinkRequest(BaseModel):
    drive_link: str

def extract_folder_id(link: str) -> str:
    patterns = [r'folders/([a-zA-Z0-9-_]+)', r'id=([a-zA-Z0-9-_]+)']
    for p in patterns:
        match = re.search(p, link)
        if match: return match.group(1)
    return link.strip()

def fetch_files_recursive(folder_id, current_path, api_key):
    items = []
    url = f"https://www.googleapis.com/drive/v3/files?q='{folder_id}'+in+parents+and+trashed=false&fields=files(id,name,mimeType)&key={api_key}"
    
    try:
        resp = http_requests.get(url).json()
        files = resp.get('files', [])
        for f in files:
            mime = f.get('mimeType', '').lower()
            name = f['name']
            if 'folder' in mime:
                new_path = f"{current_path} > {name}" if current_path else name
                items.append({"id": f['id'], "name": name, "type": "folder", "path": new_path})
                items.extend(fetch_files_recursive(f['id'], new_path, api_key))
            elif 'image' in mime or any(name.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                items.append({"id": f['id'], "name": name, "type": "image", "path": f"{current_path}/{name}" if current_path else f"All Photos/{name}"})
    except Exception: pass
    return items

@api_router.post("/drive/folder")
async def get_folder_structure(request: DriveLinkRequest):
    try:
        main_id = extract_folder_id(request.drive_link)
        all_data = fetch_files_recursive(main_id, "", API_KEY)
        return {"items": all_data, "total_images": len([i for i in all_data if i['type'] == 'image'])}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# 🔥 UPDATED: Image Compression Logic Yahan Hai
@api_router.get("/drive/image/{file_id}")
async def get_drive_image(file_id: str):
    try:
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&key={API_KEY}"
        resp = http_requests.get(url)
        
        # Original photo ko memory mein load karo
        img = Image.open(io.BytesIO(resp.content))
        
        # 1. Resize: Agar photo 1200px se badi hai toh choti karo (Loading speed badhegi)
        if img.width > 1200:
            ratio = 1200 / float(img.width)
            new_height = int(float(img.height) * float(ratio))
            img = img.resize((1200, new_height), Image.Resampling.LANCZOS)
        
        # 2. Format: JPEG mein convert karo taaki size kam ho jaye
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
            
        img_io = io.BytesIO()
        # 3. Quality: 60% quality par save karo (Isse size 90% kam ho jati hai)
        img.save(img_io, 'JPEG', quality=60, optimize=True)
        img_io.seek(0)
        
        return StreamingResponse(img_io, media_type='image/jpeg')
    except Exception as e:
        # Agar compression fail ho jaye toh original bhej do backup ke liye
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&key={API_KEY}"
        resp = http_requests.get(url, stream=True)
        return StreamingResponse(io.BytesIO(resp.content), media_type='image/jpeg')

app.include_router(api_router)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
