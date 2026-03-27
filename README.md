# 🐰 Şapşal Tavşan — Digital Memory Album
### A private anniversary gift app built with Expo + FastAPI + MongoDB

---

## 📁 Project Structure

```
sapsaltavsan/
├── backend/
│   ├── main.py
│   └── requirements.txt
└── frontend/
    ├── app/
    │   ├── _layout.tsx     ← Auth guard & navigation root
    │   ├── login.tsx       ← Password wall
    │   ├── gallery.tsx     ← Main photo/video grid + love counter
    │   └── manage.tsx      ← Admin upload & delete panel
    ├── config/
    │   └── api.ts          ← ⚠️ SET YOUR LOCAL IP HERE
    ├── hooks/
    │   └── useLoveCounter.ts
    ├── app.json
    ├── babel.config.js
    ├── package.json
    └── tsconfig.json
```

---

## ⚙️ Prerequisites

- **Python 3.10+**
- **Node.js 18+**
- **MongoDB** running locally (`mongod`) — or use [MongoDB Atlas](https://www.mongodb.com/atlas)
- **Expo CLI**: `npm install -g expo-cli`
- **Expo Go** app on your phone (App Store / Google Play)

---

## 🔧 Step 1 — Find Your Local IP Address

Your phone and computer must be on the **same Wi-Fi network**.

```bash
# macOS / Linux
ifconfig | grep "inet " | grep -v 127.0.0.1

# Windows
ipconfig
# Look for "IPv4 Address" under your Wi-Fi adapter
```

Example result: `192.168.1.42`

---

## 🔧 Step 2 — Update the API Config

Open `frontend/config/api.ts` and replace the IP:

```typescript
const LOCAL_IP = '192.168.1.42';   // ← Your actual IP here
```

---

## 🚀 Step 3 — Run the Backend

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Make sure MongoDB is running:
# macOS:   brew services start mongodb-community
# Linux:   sudo systemctl start mongod
# Windows: Start MongoDB service from Services panel

# Start the API server
python main.py
```

The backend will start at: **http://0.0.0.0:8000**
Test it at: http://localhost:8000/docs (Swagger UI)

---

## 📱 Step 4 — Run the Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start Expo
npx expo start
```

Then:
- **Mobile (Expo Go)**: Scan the QR code with your phone camera (iOS) or the Expo Go app (Android)
- **Web**: Press `w` in the terminal to open in browser

---

## 🔑 Passwords

| Role  | Password   | Access                     |
|-------|------------|----------------------------|
| User  | `280126`   | View gallery & counter     |
| Admin | `ec280126` | View + upload + delete     |

The `/manage` route is only accessible when logged in as admin.

---

## 💡 Tips & Notes

### Adding a Background Photo to Login
Replace the `LinearGradient` in `app/login.tsx` with:
```tsx
<ImageBackground source={require('../assets/your-photo.jpg')} style={StyleSheet.absoluteFill} resizeMode="cover">
  <View style={{ ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(255,100,130,0.45)' }} />
</ImageBackground>
```

### MongoDB Atlas (Cloud)
If you want to use cloud MongoDB instead of local:
```bash
# Set env variable before running
MONGO_URL="mongodb+srv://user:pass@cluster.mongodb.net" python main.py
```

### Fixing "Network Request Failed" on Phone
1. Check your LOCAL_IP in `config/api.ts` is correct
2. Make sure phone and computer are on the **same Wi-Fi**
3. Check your firewall isn't blocking port 8000:
   - macOS: System Preferences → Security → Firewall → allow Python
   - Windows: Allow Python in Windows Defender Firewall

### Video Playback
The gallery shows a ▶ badge on video cards. Full video playback in the viewer requires `expo-av` — for the basic model the viewer shows the first frame. To enable full playback, replace the `Image` in `MediaViewer` with:
```tsx
import { Video } from 'expo-av';
// ...
{memory.fileType === 'video'
  ? <Video source={{ uri: mediaUrl(memory.fileId) }} style={vw.image} useNativeControls shouldPlay />
  : <Image source={{ uri: mediaUrl(memory.fileId) }} style={vw.image} resizeMode="contain" />
}
```

---

## ✨ Features

- 🔐 Password-protected login with shake animation on wrong entry
- 💕 Live love counter (days · hours · minutes · seconds since Jan 28, 2026)
- 📷 Scrollable 2-column memory grid with image/video cards
- 🎬 GridFS video streaming with HTTP range support
- 🗂️ Admin panel: upload, caption, date, delete
- 🔄 Logout fully clears AsyncStorage — no back-navigation loophole
- 🌸 Pink & powder pink romantic theme throughout
- 📱 Works on iOS, Android (Expo Go), and Web

---

## 🐛 Troubleshooting

| Problem | Fix |
|---------|-----|
| `Error 500` on Expo start | Check `LOCAL_IP` in `config/api.ts` |
| "Cannot connect to MongoDB" | Run `mongod` and check port 27017 |
| Login loop / can't logout | `AsyncStorage.clear()` is called — restart Expo Go app |
| Images not loading on phone | Confirm phone is on same Wi-Fi, check IP |
| `expo-router` not found | Run `npm install` again in `/frontend` |

---

*Made with 💕 as a 2-month anniversary gift*
