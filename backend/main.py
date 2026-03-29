import os
import io
import json
import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket
from bson import ObjectId
import uvicorn
from PIL import Image as PILImage
import pillow_heif
from pywebpush import webpush, WebPushException
import cloudinary
import cloudinary.uploader

# HEIC desteğini aktif et
pillow_heif.register_heif_opener()

# Cloudinary config
cloudinary.config(
    cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME", "tavsanci"),
    api_key    = os.environ.get("CLOUDINARY_API_KEY"),
    api_secret = os.environ.get("CLOUDINARY_API_SECRET"),
)

# -- Config --------------------------------------------------------------------
DB_NAME         = "sapsalTavsan"
USER_PASSWORD   = "280126"
ADMIN_PASSWORD  = "ec280126"
ANNIVERSARY     = datetime(2026, 1, 28, 0, 0, 0, tzinfo=timezone.utc)

VAPID_PUBLIC_KEY  = "BJEoR2NdyCXSza7O8ki5fN44ZDj3WjGsjFnGiITpWy9D6ZYLx-CKGjcm2Wqwf2-Knrk3TShL80RyWBPthS2QGvI"
VAPID_PRIVATE_KEY = "W6B3FetfUYQsOgTBXPC0KS-SAW0XYIWDHABJ3dF0Q28"
VAPID_EMAIL       = "mailto:admin@sapsaltavsan.app"

# -- App & CORS ----------------------------------------------------------------
app = FastAPI(title="Şapşal Tavşan API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -- DB Helpers ----------------------------------------------------------------
client: Optional[AsyncIOMotorClient] = None
db     = None
fs     = None

@app.on_event("startup")
async def startup():
    global client, db, fs
    uri = "mongodb+srv://cihataksoy16_db_user:EsmaCihat2026@cihat123.nxaxw7t.mongodb.net/sapsalTavsan?retryWrites=true&w=majority&appName=Cihat123"
    client = AsyncIOMotorClient(uri)
    db     = client[DB_NAME]
    fs     = AsyncIOMotorGridFSBucket(db)
    await db.memories.create_index([("date", -1)])

@app.on_event("shutdown")
async def shutdown():
    if client:
        client.close()

# -- Push Notification Helper --------------------------------------------------
async def send_push(title: str, body: str, exclude_role: str = None):
    """Gönderen kişi hariç herkese bildirim gönder"""
    try:
        cursor = db.push_tokens.find()
        async for doc in cursor:
            if exclude_role and doc.get("role") == exclude_role:
                continue
            try:
                webpush(
                    subscription_info=doc["subscription"],
                    data=json.dumps({"title": title, "body": body}),
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": VAPID_EMAIL},
                )
            except WebPushException:
                await db.push_tokens.delete_one({"_id": doc["_id"]})
    except Exception as e:
        print(f"Push error: {e}")

# -- Auth ----------------------------------------------------------------------
@app.post("/api/auth/login")
async def login(request: Request):
    body = await request.json()
    password = body.get("password", "")
    now = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M")
    client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?")
    if password == ADMIN_PASSWORD:
        print(f"🦊 Admin girişi — {now} — {client_ip}")
        # Login kaydını veritabanına yaz
        await db.logins.insert_one({"role": "admin", "ip": client_ip, "time": datetime.now(timezone.utc)})
        return {"role": "admin", "ok": True}
    if password == USER_PASSWORD:
        print(f"🐰 User girişi — {now} — {client_ip}")
        await db.logins.insert_one({"role": "user", "ip": client_ip, "time": datetime.now(timezone.utc)})
        return {"role": "user", "ok": True}
    print(f"❌ Hatalı şifre — {now} — {client_ip}")
    raise HTTPException(status_code=401, detail="Yanlış şifre 💔")

@app.get("/api/admin/logins")
async def get_logins():
    """Son 20 girişi göster — bu URL'i sadece sen bil"""
    cursor = db.logins.find().sort("time", -1).limit(20)
    result = []
    async for doc in cursor:
        result.append({
            "role": doc["role"],
            "ip":   doc["ip"],
            "time": doc["time"].strftime("%d.%m.%Y %H:%M") if hasattr(doc["time"], "strftime") else str(doc["time"]),
        })
    return result

# -- Push Token ----------------------------------------------------------------
@app.post("/api/push/register")
async def register_push(request: Request):
    body = await request.json()
    subscription = body.get("subscription")
    role = body.get("role", "user")
    if not subscription:
        raise HTTPException(400, "subscription gerekli")
    await db.push_tokens.update_one(
        {"subscription.endpoint": subscription["endpoint"]},
        {"$set": {"subscription": subscription, "role": role, "updatedAt": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return {"ok": True}

@app.get("/api/push/vapid-public-key")
async def get_vapid_public_key():
    return {"publicKey": VAPID_PUBLIC_KEY}

# -- Status (Mod) --------------------------------------------------------------
@app.get("/api/status")
async def get_status():
    doc = await db.status.find_one({})
    if not doc:
        return {"emoji": "🐰", "text": "Seni seviyorum", "updatedAt": ""}
    return {
        "emoji": doc.get("emoji", "🐰"),
        "text": doc.get("text", ""),
        "updatedAt": doc.get("updatedAt", ""),
    }

@app.post("/api/status")
async def set_status(request: Request):
    body  = await request.json()
    emoji = body.get("emoji", "🐰")
    text  = body.get("text", "")
    role  = body.get("role", "user")
    await db.status.replace_one(
        {},
        {"emoji": emoji, "text": text, "updatedAt": datetime.now(timezone.utc).isoformat()},
        upsert=True,
    )
    sender = "Tilki 🦊" if role == "admin" else "Tavşan 🐰"
    await send_push(
        title=f"{sender} → {emoji}",
        body=text or "modunu güncelledi",
        exclude_role=role,
    )
    return {"ok": True}

# -- Song of the Day -----------------------------------------------------------
@app.get("/api/song")
async def get_song():
    doc = await db.song.find_one({})
    if not doc:
        return {"url": "", "title": "", "updatedAt": ""}
    return {
        "url": doc.get("url", ""),
        "title": doc.get("title", ""),
        "updatedAt": doc.get("updatedAt", ""),
    }

@app.post("/api/song")
async def set_song(request: Request):
    body  = await request.json()
    url   = body.get("url", "")
    title = body.get("title", "")
    role  = body.get("role", "user")
    await db.song.replace_one(
        {},
        {"url": url, "title": title, "updatedAt": datetime.now(timezone.utc).isoformat()},
        upsert=True,
    )
    sender = "Tilki 🦊" if role == "admin" else "Tavşan 🐰"
    await send_push(
        title=f"🎵 {sender} sana bir şarkı seçti",
        body=title or url,
        exclude_role=role,
    )
    return {"ok": True}

# -- Anniversary Counter -------------------------------------------------------
@app.get("/api/anniversary")
async def anniversary():
    now   = datetime.now(timezone.utc)
    delta = now - ANNIVERSARY
    total_seconds = int(delta.total_seconds())
    return {
        "days":    delta.days,
        "hours":   (total_seconds % 86400) // 3600,
        "minutes": (total_seconds % 3600)  // 60,
        "seconds": total_seconds % 60,
    }

# -- Memories ------------------------------------------------------------------
@app.get("/api/memories")
async def list_memories():
    cursor = db.memories.find().sort("date", -1)
    memories = []
    async for doc in cursor:
        # Cloudinary URL varsa onu kullan, yoksa eski GridFS fileId ile
        file_id = str(doc.get("fileId", ""))
        media_url = doc.get("mediaUrl") or (f"/api/media/{file_id}" if file_id else "")
        memories.append({
            "id":       str(doc["_id"]),
            "caption":  doc.get("caption", ""),
            "date":     doc.get("date", ""),
            "fileId":   file_id,
            "mediaUrl": media_url,
            "fileType": doc.get("fileType", "image"),
        })
    return memories

@app.post("/api/memories")
async def create_memory(
    file:    UploadFile = File(...),
    caption: str        = Form(""),
    date:    str        = Form(""),
):
    data         = await file.read()
    file_type    = "video" if file.content_type and "video" in file.content_type else "image"
    content_type = file.content_type or "image/jpeg"
    filename     = file.filename or "upload"

    # HEIC → JPEG dönüştür
    if content_type in ("image/heic", "image/heif") or filename.lower().endswith((".heic", ".heif")):
        try:
            img = PILImage.open(io.BytesIO(data))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=90)
            data = buf.getvalue()
            content_type = "image/jpeg"
            file_type = "image"
        except Exception as e:
            raise HTTPException(400, f"HEIC dönüştürme hatası: {e}")

    # Cloudinary'e yükle
    resource_type = "video" if file_type == "video" else "image"
    upload_result = cloudinary.uploader.upload(
        data,
        resource_type=resource_type,
        folder="sapsaltavsan",
    )
    media_url = upload_result["secure_url"]
    public_id = upload_result["public_id"]

    doc = {
        "caption":   caption,
        "date":      date or datetime.now(timezone.utc).isoformat(),
        "mediaUrl":  media_url,
        "publicId":  public_id,
        "fileType":  file_type,
        "createdAt": datetime.now(timezone.utc),
    }
    result = await db.memories.insert_one(doc)
    return {"id": str(result.inserted_id), "ok": True}

@app.delete("/api/memories/{memory_id}")
async def delete_memory(memory_id: str):
    doc = await db.memories.find_one({"_id": ObjectId(memory_id)})
    if not doc:
        raise HTTPException(404, "Anı bulunamadı")
    # Cloudinary'den sil
    if doc.get("publicId"):
        try:
            resource_type = "video" if doc.get("fileType") == "video" else "image"
            cloudinary.uploader.destroy(doc["publicId"], resource_type=resource_type)
        except Exception:
            pass
    # GridFS'ten sil (eski kayıtlar için)
    if doc.get("fileId"):
        try:
            await fs.delete(doc["fileId"])
        except Exception:
            pass
    await db.memories.delete_one({"_id": ObjectId(memory_id)})
    return {"ok": True}

# -- Media Streaming -----------------------------------------------------------
@app.get("/api/media/{file_id}")
async def stream_media(file_id: str, request: Request):
    try:
        oid = ObjectId(file_id)
    except Exception:
        raise HTTPException(400, "Geçersiz dosya ID")
    file_doc = await db["fs.files"].find_one({"_id": oid})
    if not file_doc:
        raise HTTPException(404, "Dosya bulunamadı")
    content_type = (file_doc.get("metadata") or {}).get("contentType", "application/octet-stream")
    file_length  = file_doc["length"]
    range_header = request.headers.get("range")
    if range_header and "video" in content_type:
        range_val   = range_header.strip().replace("bytes=", "")
        start_str, _, end_str = range_val.partition("-")
        start = int(start_str) if start_str else 0
        end   = int(end_str)   if end_str   else file_length - 1
        end   = min(end, file_length - 1)
        chunk_size = end - start + 1
        async def range_generator():
            stream = await fs.open_download_stream(oid)
            skipped = 0
            async for chunk in stream:
                if skipped + len(chunk) <= start:
                    skipped += len(chunk)
                    continue
                offset = max(0, start - skipped)
                data   = chunk[offset:]
                skipped += len(chunk)
                if len(data) > chunk_size:
                    yield data[:chunk_size]
                    break
                chunk_size -= len(data)
                yield data
                if chunk_size <= 0:
                    break
        return StreamingResponse(
            range_generator(),
            status_code=206,
            media_type=content_type,
            headers={
                "Content-Range":  f"bytes {start}-{end}/{file_length}",
                "Accept-Ranges":  "bytes",
                "Content-Length": str(end - start + 1),
            },
        )
    async def full_generator():
        stream = await fs.open_download_stream(oid)
        async for chunk in stream:
            yield chunk
    return StreamingResponse(
        full_generator(),
        media_type=content_type,
        headers={
            "Accept-Ranges":  "bytes",
            "Content-Length": str(file_length),
        },
    )

# -- Comments -----------------------------------------------------------------
@app.get("/api/memories/{memory_id}/comments")
async def get_comments(memory_id: str):
    cursor = db.comments.find({"memoryId": memory_id}).sort("createdAt", 1)
    comments = []
    async for doc in cursor:
        comments.append({
            "id":        str(doc["_id"]),
            "text":      doc.get("text", ""),
            "role":      doc.get("role", "user"),
            "createdAt": doc["createdAt"].strftime("%d.%m.%Y %H:%M") if hasattr(doc.get("createdAt"), "strftime") else "",
        })
    return comments

@app.post("/api/memories/{memory_id}/comments")
async def add_comment(memory_id: str, request: Request):
    body = await request.json()
    text = body.get("text", "").strip()
    role = body.get("role", "user")
    if not text:
        raise HTTPException(400, "Yorum boş olamaz")
    doc = {
        "memoryId":  memory_id,
        "text":      text,
        "role":      role,
        "createdAt": datetime.now(timezone.utc),
    }
    result = await db.comments.insert_one(doc)
    sender = "Tilki 🦊" if role == "admin" else "Tavşan 🐰"
    await send_push(
        title=f"💬 {sender} yorum yaptı",
        body=text[:60],
        exclude_role=role,
    )
    return {"id": str(result.inserted_id), "ok": True}

@app.delete("/api/memories/{memory_id}/comments/{comment_id}")
async def delete_comment(memory_id: str, comment_id: str):
    await db.comments.delete_one({"_id": ObjectId(comment_id)})
    return {"ok": True}

# -- User Upload (Esma da yükleyebilsin) ---------------------------------------
@app.post("/api/user/memories")
async def create_memory_user(
    file:    UploadFile = File(...),
    caption: str        = Form(""),
    date:    str        = Form(""),
):
    """User (Esma) da fotoğraf yükleyebilsin"""
    data         = await file.read()
    file_type    = "video" if file.content_type and "video" in file.content_type else "image"
    content_type = file.content_type or "image/jpeg"
    filename     = file.filename or "upload"

    if content_type in ("image/heic", "image/heif") or filename.lower().endswith((".heic", ".heif")):
        try:
            img = PILImage.open(io.BytesIO(data))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=90)
            data = buf.getvalue()
            file_type = "image"
        except Exception as e:
            raise HTTPException(400, f"HEIC dönüştürme hatası: {e}")

    resource_type = "video" if file_type == "video" else "image"
    upload_result = cloudinary.uploader.upload(
        data,
        resource_type=resource_type,
        folder="sapsaltavsan",
    )
    doc = {
        "caption":    caption,
        "date":       date or datetime.now(timezone.utc).isoformat(),
        "mediaUrl":   upload_result["secure_url"],
        "publicId":   upload_result["public_id"],
        "fileType":   file_type,
        "createdAt":  datetime.now(timezone.utc),
        "uploadedBy": "user",
    }
    result = await db.memories.insert_one(doc)
    await send_push(
        title="🐰 Tavşan yeni bir anı ekledi!",
        body=caption or "Yeni bir fotoğraf yüklendi",
        exclude_role="user",
    )
    return {"id": str(result.inserted_id), "ok": True}

# -- Run -----------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=10000)
