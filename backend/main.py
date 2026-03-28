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

# HEIC desteğini aktif et
pillow_heif.register_heif_opener()

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
async def send_push(title: str, body: str):
    """Tüm kayıtlı push token'larına bildirim gönder — ikisine de gider"""
    try:
        cursor = db.push_tokens.find()
        async for doc in cursor:
            try:
                webpush(
                    subscription_info=doc["subscription"],
                    data=json.dumps({"title": title, "body": body}),
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": VAPID_EMAIL},
                )
            except WebPushException:
                # Geçersiz token, sil
                await db.push_tokens.delete_one({"_id": doc["_id"]})
    except Exception as e:
        print(f"Push error: {e}")

# -- Auth ----------------------------------------------------------------------
@app.post("/api/auth/login")
async def login(request: Request):
    body = await request.json()
    password = body.get("password", "")
    if password == ADMIN_PASSWORD:
        return {"role": "admin", "ok": True}
    if password == USER_PASSWORD:
        return {"role": "user", "ok": True}
    raise HTTPException(status_code=401, detail="Yanlış şifre 💔")

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
    sender = "Cihat" if role == "admin" else "Esma"
    await send_push(
        title=f"{sender} modunu güncelledi {emoji}",
        body=text or f"Yeni mod: {emoji}",
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
    sender = "Cihat" if role == "admin" else "Esma"
    await send_push(
        title=f"🎵 {sender} günün şarkısını seçti!",
        body=title or url,
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
        memories.append({
            "id":       str(doc["_id"]),
            "caption":  doc.get("caption", ""),
            "date":     doc.get("date", ""),
            "fileId":   str(doc.get("fileId", "")),
            "fileType": doc.get("fileType", "image"),
        })
    return memories

@app.post("/api/memories")
async def create_memory(
    file:    UploadFile = File(...),
    caption: str        = Form(""),
    date:    str        = Form(""),
):
    content      = await file.read()
    file_type    = "video" if file.content_type and "video" in file.content_type else "image"
    content_type = file.content_type or "image/jpeg"
    filename     = file.filename or "upload"

    if content_type in ("image/heic", "image/heif") or filename.lower().endswith((".heic", ".heif")):
        try:
            img = PILImage.open(io.BytesIO(content))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=90)
            content = buf.getvalue()
            content_type = "image/jpeg"
            filename = os.path.splitext(filename)[0] + ".jpg"
        except Exception as e:
            raise HTTPException(400, f"HEIC dönüştürme hatası: {e}")

    file_id = await fs.upload_from_stream(
        filename,
        io.BytesIO(content),
        metadata={"contentType": content_type},
    )
    doc = {
        "caption":   caption,
        "date":      date or datetime.now(timezone.utc).isoformat(),
        "fileId":    file_id,
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

# -- Run -----------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=10000)
