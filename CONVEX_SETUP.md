# Convex Setup Instructions

This app uses Convex to store processed video data and avoid reprocessing videos.

## Setup Steps

1. **Create a Convex Account**
   - Go to https://www.convex.dev/
   - Sign up for a free account

2. **Create a New Project**
   - Click "New Project" in your Convex dashboard
   - Choose a project name (e.g., "lex-minus-lex")

3. **Install Convex CLI and Login**
   ```bash
   npm install -g convex
   npx convex login
   ```

4. **Link Your Project**
   ```bash
   npx convex dev --once
   ```
   - Select your project when prompted
   - This will create a `.env.local` file with your `NEXT_PUBLIC_CONVEX_URL`

5. **Deploy the Schema**
   ```bash
   npx convex deploy
   ```

## Features

- **Caching**: Videos are automatically cached after processing
- **Cost Tracking**: See how much each video costs to process
- **History Page**: View all previously processed videos at `/history`
- **Statistics**: Track total videos processed, time, and costs

## Cost Breakdown

Processing costs are calculated based on:
- YouTube Download: ~$0.0033 per video (CPU)
- Diarization: ~$0.0135 per minute of video (T4 GPU)
- Processing: ~$0.0133 per video (CPU)

For a 10-minute podcast, expect costs around $0.15-0.20.