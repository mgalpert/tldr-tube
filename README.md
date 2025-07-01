# TLDR Tube

✂️ Automatically cut any YouTube video down to the most important parts or isolate podcast guest speakers.

---

## 🔗 Web (Next.js) App

To run the TLDR Tube web application locally:

### 1. Install dependencies

```bash
npm install
# or
yarn
# or
pnpm install
# or
bun install
```

### 2. Start the development server

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

### 3. Set up environment variables

Create a `.env.local` file in the root of the project and add your Sieve API key:

```
SIEVE_KEY=your_sieve_api_key_here
```

Then open [http://localhost:3000](http://localhost:3000) in your browser to view the app.

---

## 🧠 Backend (Sieve Functions)

The backend logic for segment download and processing lives in the `sieve-functions/` directory.

### 1. Set up environment variables

Create a `.env` file inside the `sieve-functions/` directory:

```
OPENAI_KEY=your_openai_api_key_here
```

### 2. Install dependencies

Navigate into the `sieve-functions/` directory and run:

```bash
pip install -r requirements.txt
```

### 3. Deploy your Sieve function

First, log in using your Sieve API key:

```bash
sieve login
```

Then deploy the function:

```bash
sieve deploy create_video.py
```

---

## 🎙️ Guest Isolation Feature

The new "Guest Only" mode uses Sieve's speaker diarization API to:
1. Download the podcast video from YouTube
2. Extract audio and perform speaker diarization
3. Identify which speaker is the guest (typically speaks less than the host)
4. Return segments containing only the guest's speaking parts

### Deploy the guest isolation function:

```bash
sieve deploy isolate_guest.py
```

## ✅ Summary

- Web UI is built with **Next.js**
- Video analysis and segmentation is powered by **Sieve functions**
  - `create_video.py` - TLDR summarization
  - `isolate_guest.py` - Guest speaker isolation
- Requires **Sieve** and **OpenAI** API keys
- Simple local setup for development and deployment
