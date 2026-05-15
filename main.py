import os
import base64
import mimetypes
import uuid
import json
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from contextlib import asynccontextmanager

import dashscope
from dashscope.aigc.image_generation import ImageGeneration
from dashscope.api_entities.dashscope_response import Message
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).parent.resolve()
load_dotenv(BASE_DIR / ".env")

OUTPUTS_DIR = BASE_DIR / "outputs"
SESSIONS_DIR = BASE_DIR / "sessions"
UPLOADS_DIR = BASE_DIR / "uploads"
OUTPUTS_DIR.mkdir(exist_ok=True)
SESSIONS_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)

dashscope.base_http_api_url = "https://dashscope.aliyuncs.com/api/v1"

MAX_IMAGES_PER_REQUEST = 5

def get_file_url(file_path: str) -> str:
    return f"file://{os.path.abspath(file_path)}"

class SessionManager:
    def __init__(self):
        self.sessions: dict[str, dict] = {}

    def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = {
            "id": session_id,
            "created_at": datetime.now().isoformat(),
            "messages": [],
            "all_images": []
        }
        self._save_session(session_id)
        return session_id

    def get_session(self, session_id: str) -> Optional[dict]:
        session_file = SESSIONS_DIR / f"{session_id}.json"
        if session_file.exists():
            with open(session_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def _save_session(self, session_id: str):
        if session_id in self.sessions:
            session_file = SESSIONS_DIR / f"{session_id}.json"
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump(self.sessions[session_id], f, ensure_ascii=False, indent=2)

    def update_session(self, session_id: str, messages: List[dict], all_images: List[str]):
        session = self.get_session(session_id)
        if session:
            session["messages"] = messages
            session["all_images"] = all_images
            self.sessions[session_id] = session
            self._save_session(session_id)

    def get_all_sessions(self) -> List[dict]:
        sessions = []
        for session_file in SESSIONS_DIR.glob("*.json"):
            with open(session_file, "r", encoding="utf-8") as f:
                sessions.append(json.load(f))
        return sorted(sessions, key=lambda x: x["created_at"], reverse=True)

    def delete_session(self, session_id: str) -> bool:
        session_file = SESSIONS_DIR / f"{session_id}.json"
        if session_file.exists():
            session_file.unlink()
            if session_id in self.sessions:
                del self.sessions[session_id]
            return True
        return False

session_manager = SessionManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("生图服务已启动")
    yield
    print("生图服务已关闭")

app = FastAPI(title="生图 WebUI", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def home():
    return FileResponse("static/index.html")

@app.get("/api/sessions")
async def list_sessions():
    sessions = session_manager.get_all_sessions()
    return JSONResponse({"sessions": sessions})

@app.post("/api/sessions")
async def create_session():
    session_id = session_manager.create_session()
    return JSONResponse({"session_id": session_id})

@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    success = session_manager.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return JSONResponse({"success": True})

@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return JSONResponse(session)

@app.get("/api/images")
async def list_all_images():
    images = []
    for img_file in sorted(UPLOADS_DIR.glob("*"), key=lambda x: x.stat().st_mtime, reverse=True):
        if img_file.suffix.lower() in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"]:
            images.append({
                "filename": img_file.name,
                "path": str(img_file),
                "url": f"/api/uploads/{img_file.name}",
                "type": "upload",
                "created_at": datetime.fromtimestamp(img_file.stat().st_mtime).isoformat()
            })
    return JSONResponse({"images": images})

@app.get("/api/outputs")
async def list_output_images():
    images = []
    for img_file in sorted(OUTPUTS_DIR.glob("*.png"), key=lambda x: x.stat().st_mtime, reverse=True):
        images.append({
            "filename": img_file.name,
            "path": str(img_file),
            "url": f"/api/images/{img_file.name}",
            "type": "output",
            "created_at": datetime.fromtimestamp(img_file.stat().st_mtime).isoformat()
        })
    return JSONResponse({"images": images})

@app.delete("/api/images/{filename}")
async def delete_image(filename: str):
    if filename.startswith("output_"):
        img_path = OUTPUTS_DIR / filename
    else:
        img_path = UPLOADS_DIR / filename

    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")

    img_path.unlink()
    return JSONResponse({"success": True})

@app.post("/api/upload")
async def upload_image(files: List[UploadFile] = File(...)):
    try:
        uploaded_files = []
        for file in files:
            file_id = str(uuid.uuid4())
            suffix = Path(file.filename).suffix if file.filename else ".png"
            file_path = UPLOADS_DIR / f"{file_id}{suffix}"

            content = await file.read()
            with open(file_path, "wb") as f:
                f.write(content)

            uploaded_files.append({
                "file_id": file_id,
                "file_path": str(file_path),
                "file_url": f"/api/uploads/{file_id}{suffix}"
            })

        return JSONResponse({
            "uploaded_files": uploaded_files
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/generate")
async def generate_image(
    session_id: str = Form(...),
    prompt: str = Form(...),
    selected_images: str = Form(default=""),
    size: str = Form(default="2K")
):
    try:
        if not prompt or not prompt.strip():
            raise HTTPException(status_code=400, detail="提示词不能为空")

        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="API key not configured")

        session = session_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        selected_list = []
        if selected_images:
            selected_list = [img.strip() for img in selected_images.split(",") if img.strip()]

        if len(selected_list) > MAX_IMAGES_PER_REQUEST:
            raise HTTPException(status_code=400, detail=f"最多只能选择{MAX_IMAGES_PER_REQUEST}张图片")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"output_{session_id}_{timestamp}.png"
        output_path = OUTPUTS_DIR / output_filename

        content = []
        content.append({"text": prompt})

        for img_path in selected_list:
            if img_path.startswith("/api/"):
                img_path = img_path.replace("/api/uploads/", str(UPLOADS_DIR) + "/")
                img_path = img_path.replace("/api/images/", str(OUTPUTS_DIR) + "/")
            if not img_path.startswith("file://"):
                img_path = f"file://{os.path.abspath(img_path)}"
            content.append({"image": img_path})

        message = Message(role="user", content=content)

        print(f"Generating image with {len(selected_list)} reference images")
        print(f"Content: {content}")

        rsp = ImageGeneration.call(
            model="wan2.7-image-pro",
            api_key=api_key,
            messages=[message],
            watermark=False,
            n=1,
            size=size
        )

        if rsp.status_code != 200:
            print(f"API Error: status={rsp.status_code}, message={rsp.message}")
            raise HTTPException(status_code=rsp.status_code, detail=f"生成失败: {rsp.message}")

        result_image_url = None
        for choice in rsp.output.choices:
            for content_item in choice["message"]["content"]:
                if content_item.get("type") == "image":
                    image_url = content_item["image"]
                    urllib.request.urlretrieve(image_url, output_path)
                    result_image_url = f"/api/images/{output_filename}"
                    break

        if not result_image_url:
            raise HTTPException(status_code=500, detail="未获取到生成的图片")

        messages = session.get("messages", [])
        messages.append({
            "role": "user",
            "content": prompt,
            "reference_images": selected_list,
            "output_image": result_image_url,
            "timestamp": datetime.now().isoformat()
        })
        messages.append({
            "role": "assistant",
            "content": "图像生成完成",
            "image": result_image_url,
            "timestamp": datetime.now().isoformat()
        })

        all_images = session.get("all_images", [])
        all_images.append(result_image_url)
        session_manager.update_session(session_id, messages, all_images)

        return JSONResponse({
            "success": True,
            "image": result_image_url,
            "session": session
        })

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Error: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/images/{filename}")
async def get_image(filename: str):
    image_path = OUTPUTS_DIR / filename
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(image_path)

@app.get("/api/uploads/{filename}")
async def get_uploaded_image(filename: str):
    image_path = UPLOADS_DIR / filename
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(image_path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
