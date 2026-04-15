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

API_KEY = os.getenv('GOOGLE_API_KEY')

class DriveLinkRequest(BaseModel):
    drive_link: str

def extract_folder_id(link: str) -> str:
    patterns = [r'folders/([a-zA-Z0-9-_]+)', r'id=([a-zA-Z0-9-_]+)']
    for p in patterns:
        match = re.search(p, link)
        if match: return match.group(1)
    return link.strip()

# --- RECURSIVE FUNCTION: Har kamre ke andar ka saaman nikaalo ---
def fetch_files_recursive(folder_id, current_path, api_key):
    items = []
    # Google se files ki list maango
    url = f"https://www.googleapis.com/drive/v3/files?q='{folder_id}'+in+parents+and+trashed=false&fields=files(id,name,mimeType)&key={api_key}"
    
    try:
        resp = http_requests.get(url).json()
        files = resp.get('files', [])
        
        for f in files:
            mime = f.get('mimeType', '').lower()
            name = f['name']
            
            if 'folder' in mime:
                # 1. Folder ka naam register karo (jaise 'ATP - COURT ROAD')
                new_path = f"{current_path} > {name}" if current_path else name
                items.append({
                    "id": f['id'],
                    "name": name,
                    "type": "folder",
                    "path": new_path
                })
                # 2. Iske andar phir se ghuso (Recursion)
                items.extend(fetch_files_recursive(f['id'], new_path, api_key))
            
            elif 'image' in mime or any(name.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                # 3. Image mil gayi!
                items.append({
                    "id": f['id'],
                    "name": name,
                    "type": "image",
                    "path": f"{current_path}/{name}" if current_path else f"Uncategorized/{name}"
                })
    except Exception as e:
        print(f"Error: {e}")
        
    return items

@api_router.post("/drive/folder")
async def get_folder_structure(request: DriveLinkRequest):
    try:
        main_id = extract_folder_id(request.drive_link)
        # Gehrayi tak scanning shuru
        all_data = fetch_files_recursive(main_id, "", API_KEY)
        
        return {
            "items": all_data,
            "folder_name": "Kushal's NSO Gallery",
            "total_images": len([i for i in all_data if i['type'] == 'image']),
            "total_folders": len([i for i in all_data if i['type'] == 'folder'])
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
