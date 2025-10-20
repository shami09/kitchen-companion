// server/index.js
import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import { AccessToken, RoomServiceClient } from 'livekit-server-sdk';

const app = express();
app.use(express.json());
app.use(
  cors({
    origin: process.env.CORS_ORIGIN || 'http://localhost:5173',
    credentials: true,
  })
);

const { LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, PORT } = process.env;

// RoomServiceClient must use HTTPS (convert wss -> https)
const API_BASE =
  LIVEKIT_URL?.startsWith('wss:')
    ? LIVEKIT_URL.replace(/^wss:/, 'https:')
    : LIVEKIT_URL;

const roomSvc =
  LIVEKIT_URL && LIVEKIT_API_KEY && LIVEKIT_API_SECRET
    ? new RoomServiceClient(API_BASE, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
    : null;

app.get('/', (_req, res) => {
  res
    .type('text/plain')
    .send('LiveKit Token Server is running. Use /token?room=<room>&identity=<id>');
});

app.get('/health', (_req, res) => {
  res.json({ ok: true, url: LIVEKIT_URL || null, apiBase: API_BASE || null });
});

app.get('/token', async (req, res) => {
  try {
    if (!LIVEKIT_URL || !LIVEKIT_API_KEY || !LIVEKIT_API_SECRET) {
      console.error('Missing LIVEKIT_URL/API_KEY/API_SECRET');
      return res.status(500).json({ error: 'server misconfigured' });
    }
    const room = (req.query.room || 'KitchenCompanion').toString();
    const identity = (req.query.identity || `user-${Math.random().toString(36).slice(2,8)}`).toString();

    // Create the join token
    const at = new AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET, { identity, name: identity });
    at.addGrant({ roomJoin: true, room, canPublish: true, canSubscribe: true, canPublishData: true });
    const token = await at.toJwt();

    //  LiveKit transcription - using Browser STT instead

    if (roomSvc) {
      try {
        await roomSvc.startTranscription({
          room,
          engine: process.env.STT_ENGINE || 'whisper',
        });
        console.log(`[transcription] started for room=${room}`);
      } catch (e) {
        console.log('[transcription] start notice:', e?.message || e);
      }
    }


    console.log(`[token] room=${room} identity=${identity} len=${token.length}`);
    res.json({ token, url: LIVEKIT_URL, room, identity });
  } catch (e) {
    console.error('Token error:', e);
    res.status(500).json({ error: String(e?.message || e) });
  }
});

const port = Number(PORT || 8787);
app.listen(port, '0.0.0.0', () => console.log(`Token server on http://localhost:${port}`));