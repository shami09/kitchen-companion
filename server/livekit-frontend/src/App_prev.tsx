import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Room, RoomEvent, RemoteParticipant, RemoteTrackPublication, Track, createLocalAudioTrack } from 'livekit-client';

type TranscriptLine = {
  id: string;
  participant: string;
  text: string;
  isFinal: boolean;
};

const SERVER_BASE = import.meta.env.VITE_TOKEN_SERVER || 'http://localhost:8787';

export default function App() {
  const [room, setRoom] = useState<Room | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [connected, setConnected] = useState(false);
  const [identity, setIdentity] = useState<string>('');
  const [roomName, setRoomName] = useState<string>('KitchenCompanion');
  const [transcript, setTranscript] = useState<TranscriptLine[]>([]);
  const audioRef = useRef<HTMLAudioElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // autoscroll transcript
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [transcript]);

  const handleTranscription = useCallback((evt: any) => {
    // LiveKit JS SDK emits RoomEvent.TranscriptionReceived when transcription is enabled
    // evt generally has: participant, trackSid, timestamp, segments[]
    // Segment: { text, final, id, speaker? }
    const segments = evt?.segments ?? [];
    setTranscript(prev => {
      const next = [...prev];
      for (const seg of segments) {
        const id = seg.id || `${evt.trackSid}-${seg.startTime ?? Date.now()}`;
        const who = evt?.participant?.name || evt?.participant?.identity || 'Speaker';
        const idx = next.findIndex(l => l.id === id);
        if (idx >= 0) {
          next[idx] = { ...next[idx], text: seg.text, isFinal: !!seg.final };
        } else {
          next.push({ id, participant: who, text: seg.text, isFinal: !!seg.final });
        }
      }
      return next;
    });
  }, []);

  const attachRemoteAudio = useCallback((
    p: RemoteParticipant,
    pub: RemoteTrackPublication
  ) => {
    if (pub.kind === Track.Kind.Audio && pub.audioTrack) {
      // Play remote audio (agent) through a hidden <audio> element.
      const el = audioRef.current;
      if (!el) return;
      pub.audioTrack.attach(el);
      el.play().catch(() => {
        // Browser might require user gesture. Start Call button click usually satisfies it.
      });
    }
  }, []);

  const onTrackSubscribed = useCallback((track, pub, participant) => {
    if (pub.kind === Track.Kind.Audio) attachRemoteAudio(participant, pub);
  }, [attachRemoteAudio]);

  const startCall = useCallback(async () => {
    setConnecting(true);
    try {
      // fetch token from your token server
      const me = `user-${Math.random().toString(36).slice(2, 8)}`;
      const resp = await fetch(`${SERVER_BASE}/token?room=${encodeURIComponent(roomName)}&identity=${encodeURIComponent(me)}`);
      const { token, url, identity: ident } = await resp.json();

      const r = new Room({
        publishDefaults: { video: false, audioBitrate: 24000 },
        // enableDynacast: true  // optional
      });

      // wire up events
      r
        .on(RoomEvent.TrackSubscribed, onTrackSubscribed)
        .on(RoomEvent.TranscriptionReceived, handleTranscription) // live transcription stream
        .on(RoomEvent.Disconnected, () => {
          setConnected(false);
          setRoom(null);
        });

      await r.connect(url, token);
      setIdentity(ident);
      setRoom(r);
      setConnected(true);

      // publish mic
      const mic = await createLocalAudioTrack();
      await r.localParticipant.publishTrack(mic);

      // hook already-subscribed remote audio (agent) if exists
      r.participants.forEach((p) => {
        p.trackPublications.forEach((pub) => {
          if (pub.kind === Track.Kind.Audio && pub.isSubscribed && pub.audioTrack) {
            attachRemoteAudio(p, pub);
          }
        });
      });
    } catch (e) {
      console.error(e);
      alert('Could not start call. Check token server logs.');
    } finally {
      setConnecting(false);
    }
  }, [roomName, onTrackSubscribed, handleTranscription, attachRemoteAudio]);

  const endCall = useCallback(async () => {
    try {
      await room?.disconnect();
    } finally {
      setConnected(false);
      setRoom(null);
      setTranscript([]);
    }
  }, [room]);

  // Optional PDF upload (stub): POST to your server; wire to your RAG ingester
  const onUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch(`${SERVER_BASE}/upload`, { method: 'POST', body: fd });
    if (!res.ok) {
      alert('Upload failed');
      return;
    }
    alert('Uploaded (stub). Wire this endpoint to your RAG pipeline.');
    e.currentTarget.value = '';
  }, []);

  return (
    <div className="h-full bg-neutral-950 text-neutral-100 flex flex-col items-center">
      <div className="w-full max-w-3xl px-4 py-6">
        <h1 className="text-2xl font-semibold">KitchenCompanion — Voice Chat</h1>

        <div className="mt-4 flex gap-2 items-center">
          <label className="text-sm opacity-80">Room</label>
          <input
            className="px-3 py-2 rounded bg-neutral-900 border border-neutral-800"
            value={roomName}
            onChange={(e) => setRoomName(e.target.value)}
          />
          <button
            className="px-4 py-2 rounded bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50"
            onClick={startCall}
            disabled={connecting || connected}
          >
            {connecting ? 'Connecting…' : 'Start Call'}
          </button>
          <button
            className="px-4 py-2 rounded bg-rose-600 hover:bg-rose-500 disabled:opacity-50"
            onClick={endCall}
            disabled={!connected}
          >
            End Call
          </button>

          {/* Optional PDF upload */}
          <label className="ml-auto px-3 py-2 rounded bg-neutral-800 hover:bg-neutral-700 cursor-pointer">
            <input type="file" className="hidden" accept="application/pdf" onChange={onUpload} />
            Upload PDF (optional)
          </label>
        </div>

        <div className="mt-6">
          <h2 className="text-lg font-medium mb-2">Live Transcript</h2>
          <div ref={scrollRef} className="h-[50vh] overflow-auto rounded border border-neutral-800 bg-neutral-900 p-3">
            {transcript.length === 0 && (
              <div className="text-neutral-400 text-sm">Start a call to see transcripts in real time.</div>
            )}
            {transcript.map(line => (
              <div key={line.id} className="mb-2">
                <span className="text-emerald-400 font-semibold">{line.participant}:</span>{' '}
                <span className={line.isFinal ? 'opacity-100' : 'opacity-80 italic'}>
                  {line.text}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Hidden audio element for agent audio playback */}
        <audio ref={audioRef} autoPlay playsInline />
        {connected && (
          <div className="mt-2 text-xs opacity-70">
            Connected as <span className="font-mono">{identity}</span>
          </div>
        )}
      </div>
    </div>
  );
}
