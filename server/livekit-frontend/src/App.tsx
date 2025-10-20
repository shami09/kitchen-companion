// src/App.tsx - Complete corrected code with PDF upload and RAG
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Room,
  RoomEvent,
  RemoteParticipant,
  RemoteTrackPublication,
  Track,
  createLocalAudioTrack,
} from 'livekit-client';

type TranscriptLine = {
  id: string;
  participant: string;
  text: string;
  isFinal: boolean;
};

type VectorstoreInfo = {
  status: string;
  message: string;
  uploaded_pdfs?: string[];
  pdf_count?: number;
  vector_count?: number | string;
};

const SERVER_BASE: string =
  (import.meta.env.VITE_TOKEN_SERVER as string) || 'http://localhost:8787';
const UPLOAD_SERVER: string =
  (import.meta.env.VITE_UPLOAD_SERVER as string) || 'http://localhost:8788';

// -------------------- Browser STT (Web Speech API) --------------------
interface SpeechRecognition extends EventTarget {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  start(): void;
  stop(): void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: any) => void) | null;
  onend: (() => void) | null;
}

interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList;
}

interface SpeechRecognitionResultList {
  readonly length: number;
  item(index: number): SpeechRecognitionResult;
  [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionResult {
  readonly length: number;
  item(index: number): SpeechRecognitionAlternative;
  [index: number]: SpeechRecognitionAlternative;
  isFinal: boolean;
}

interface SpeechRecognitionAlternative {
  transcript: string;
  confidence: number;
}

type Recog = SpeechRecognition;

declare global {
  interface Window {
    SpeechRecognition?: new () => SpeechRecognition;
    webkitSpeechRecognition?: new () => SpeechRecognition;
  }
}

function makeSpeechRecognizer(
  onPartial: (text: string) => void,
  onFinal: (text: string) => void,
  onError: (msg: string) => void,
  onEnd: () => void
): Recog | null {
  const SR =
    window.SpeechRecognition || (window as any).webkitSpeechRecognition;
  if (!SR) return null;

  const recog = new SR() as Recog;
  recog.lang = 'en-US';
  recog.interimResults = true;
  recog.continuous = true;

  recog.onresult = (e: SpeechRecognitionEvent) => {
    const res = e.results[e.results.length - 1];
    const text = res?.[0]?.transcript ?? '';
    if (!text) return;
    if (res.isFinal) onFinal(text);
    else onPartial(text);
  };
  recog.onerror = (e: any) => {
    const msg = e?.error || e?.message || String(e);
    console.warn('[browser-stt] error:', msg);
    onError(msg);
  };
  recog.onend = () => {
    console.log('[browser-stt] ended');
    onEnd();
  };

  return recog;
}
// ---------------------------------------------------------------------

export default function App() {
  const [room, setRoom] = useState<Room | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [connected, setConnected] = useState(false);
  const [identity, setIdentity] = useState<string>('');
  const [roomName, setRoomName] = useState<string>('KitchenCompanion');
  const [transcript, setTranscript] = useState<TranscriptLine[]>([]);
  const [sttStatus, setSttStatus] = useState<string>('');
  const [sttActive, setSttActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string>('');
  const [vectorstoreInfo, setVectorstoreInfo] = useState<VectorstoreInfo | null>(null);
  
  const audioRef = useRef<HTMLAudioElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // browser STT refs
  const recogRef = useRef<Recog | null>(null);
  const partialIdRef = useRef<string | null>(null);
  const shouldRestartRef = useRef(false);

  // autoscroll transcript
  useEffect(() => {
    if (!scrollRef.current) return;
    scrollRef.current.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    });
  }, [transcript]);

  // Load vectorstore info on mount
  useEffect(() => {
    fetchVectorstoreInfo();
  }, []);

  const fetchVectorstoreInfo = async () => {
    try {
      const res = await fetch(`${UPLOAD_SERVER}/vectorstore-info`);
      if (res.ok) {
        const data = await res.json();
        setVectorstoreInfo(data);
      }
    } catch (e) {
      console.error('Failed to fetch vectorstore info:', e);
    }
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      console.log('[frontend] Component unmounting, cleaning up...');
      // Clean up STT
      shouldRestartRef.current = false;
      if (recogRef.current) {
        try {
          recogRef.current.stop();
        } catch (e) {
          console.error('[browser-stt] cleanup error:', e);
        }
        recogRef.current = null;
      }
      // Clean up room
      if (room) {
        room.disconnect().catch(console.error);
      }
    };
  }, [room]);

  // LiveKit transcription (if enabled on the room)
  const handleTranscription = useCallback((evt: any, participant: any) => {
    console.log('[LK] transcription event:', evt, 'participant:', participant?.identity);
    const segments = evt?.segments ?? [];
    if (segments.length === 0) {
      console.log('[LK] no segments in transcription event');
      return;
    }
    
    setTranscript((prev) => {
      const next = [...prev];
      for (const seg of segments) {
        if (!seg.text) continue; // Skip empty segments
        
        const id = seg.id || `${evt.trackSid}-${seg.startTime ?? Date.now()}`;
        const participantIdentity = participant?.identity || 'unknown';
        const who = participantIdentity.startsWith('user-') ? 'You (LK)' : 'Agent';
        
        console.log('[LK] Processing segment:', { id, who, identity: participantIdentity, text: seg.text });
        
        const idx = next.findIndex((l) => l.id === id);
        if (idx >= 0) {
          next[idx] = { ...next[idx], text: seg.text, isFinal: !!seg.final };
        } else {
          next.push({
            id,
            participant: who,
            text: seg.text,
            isFinal: !!seg.final,
          });
        }
      }
      return next;
    });
  }, []);

  // Attach remote audio (agent) to hidden <audio>
  const attachRemoteAudio = useCallback(
    (_p: RemoteParticipant, pub: RemoteTrackPublication) => {
      if (pub.kind !== Track.Kind.Audio || !pub.audioTrack) return;
      const el = audioRef.current;
      if (!el) return;
      pub.audioTrack.attach(el);
      el.play().catch(() => {
        /* Start button usually satisfies gesture */
      });
    },
    []
  );

  const onTrackSubscribed = useCallback(
    (_track: any, pub: RemoteTrackPublication, participant: RemoteParticipant) => {
      if (pub.kind === Track.Kind.Audio) attachRemoteAudio(participant, pub);
    },
    [attachRemoteAudio]
  );

  // ---------- START / STOP Browser STT ----------
  const startBrowserSTT = useCallback(() => {
    if (recogRef.current) {
      console.log('[browser-stt] already running');
      return;
    }

    console.log('[browser-stt] Attempting to create recognizer...');
    const recog = makeSpeechRecognizer(
      (partial) => {
        console.log('[browser-stt] PARTIAL:', partial);
        setSttStatus('🎤 Listening...');
        setTranscript((prev) => {
          const id = partialIdRef.current ?? `you-${Date.now()}`;
          partialIdRef.current = id;
          const idx = prev.findIndex((l) => l.id === id);
          if (idx >= 0) {
            const copy = [...prev];
            copy[idx] = { ...copy[idx], text: partial, isFinal: false };
            return copy;
          }
          return [...prev, { id, participant: 'Transcript', text: partial, isFinal: false }];
        });
      },
      (finalText) => {
        console.log('[browser-stt] FINAL:', finalText);
        setTranscript((prev) => {
          const id = partialIdRef.current ?? `you-${Date.now()}`;
          partialIdRef.current = null;
          const idx = prev.findIndex((l) => l.id === id);
          const base = { id, participant: 'Transcript', text: finalText, isFinal: true };
          if (idx >= 0) {
            const copy = [...prev];
            copy[idx] = { ...copy[idx], ...base };
            return copy;
          }
          return [...prev, base];
        });
      },
      (err) => {
        console.error('[browser-stt] error:', err);
        setSttStatus(`❌ STT error: ${err}`);
        if (err === 'not-allowed') {
          setSttStatus('❌ Microphone permission denied');
        }
      },
      () => {
        // Auto-restart if still connected
        if (shouldRestartRef.current && recogRef.current) {
          console.log('[browser-stt] auto-restarting...');
          setTimeout(() => {
            if (shouldRestartRef.current) {
              try {
                recogRef.current?.start();
              } catch (e) {
                console.error('[browser-stt] restart failed:', e);
              }
            }
          }, 100);
        }
      }
    );

    if (!recog) {
      const reason = 'Browser STT not supported. Use Chrome/Edge or enable LiveKit transcription.';
      console.error('[browser-stt]', reason);
      setSttStatus('⚠️ ' + reason);
      return;
    }

    console.log('[browser-stt] Recognizer created successfully');
    recogRef.current = recog;
    shouldRestartRef.current = true;
    
    try {
      console.log('[browser-stt] Calling start()...');
      recog.start();
      console.log('[browser-stt] Started successfully!');
      setSttStatus('🎤 Listening...');
      setSttActive(true);
    } catch (e: any) {
      console.error('[browser-stt] start error:', e);
      setSttStatus(`❌ STT start error: ${e?.message || e}`);
      recogRef.current = null;
    }
  }, []);

  const stopBrowserSTT = useCallback(() => {
    console.log('[browser-stt] Stopping STT...');
    shouldRestartRef.current = false;
    if (!recogRef.current) {
      console.log('[browser-stt] No recognizer to stop');
      return;
    }
    try {
      recogRef.current.stop();
      console.log('[browser-stt] stopped');
    } catch (e) {
      console.error('[browser-stt] stop error:', e);
    }
    recogRef.current = null;
    partialIdRef.current = null;
    setSttStatus('');
    setSttActive(false);
  }, []);
  // ---------------------------------------------

  const startCall = useCallback(async () => {
    console.log('[frontend] Starting new call...');
    setConnecting(true);
    setSttStatus('Requesting microphone access...');
    
    // Ensure clean state before starting
    setTranscript([]);
    setSttActive(false);
    shouldRestartRef.current = false;
    partialIdRef.current = null;
    
    try {
      // Request mic permission FIRST
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach(t => t.stop()); // Release temporary stream
      
      // fetch token
      const me = `user-${Math.random().toString(36).slice(2, 8)}`;
      const tokenUrl = `${SERVER_BASE}/token?room=${encodeURIComponent(
        roomName
      )}&identity=${encodeURIComponent(me)}`;
      console.log('[frontend] fetching token from', tokenUrl);
      
      const resp = await fetch(tokenUrl, { credentials: 'include' });
      if (!resp.ok) {
        const body = await resp.text().catch(() => '');
        throw new Error(`Token server ${resp.status}. Body: ${body.slice(0, 200)}`);
      }
      const data = await resp.json();
      const { token, url, identity: ident } = data || {};
      console.log('[frontend] token received, connecting to:', url);
      if (!token || !url) throw new Error('Bad token payload (need token & url)');

      // connect to room
      const r = new Room({
        adaptiveStream: true,
        dynacast: true,
      });
      
      r.on(RoomEvent.ConnectionStateChanged, (s) => {
        console.log('[LK] Connection state changed:', s);
        if (s === 'disconnected') {
          console.log('[LK] Room disconnected, cleaning up...');
          setConnected(false);
          setRoom(null);
          stopBrowserSTT();
        }
      });
      
      r.on(RoomEvent.Disconnected, (reason) => {
        console.log('[LK] Room disconnected event received:', reason);
        setConnected(false);
        setRoom(null);
        setSttStatus('');
        setSttActive(false);
        stopBrowserSTT();
        
        // Clear window reference
        if ((window as any).lkRoom) {
          delete (window as any).lkRoom;
        }
      });
      
      r.on(RoomEvent.TrackSubscribed, onTrackSubscribed);
      r.on(RoomEvent.TranscriptionReceived, handleTranscription);
      
      // Add participant event listeners
      r.on(RoomEvent.ParticipantConnected, (participant) => {
        console.log('[LK] Participant connected:', participant.identity, participant.isLocal ? '(local)' : '(remote)');
        if (!participant.isLocal) {
          console.log('[LK] Agent joined!');
          setSttStatus('🤖 Agent connected! Starting speech recognition...');
          // Start STT immediately when agent joins
          setTimeout(() => {
            startBrowserSTT();
          }, 500);
        }
      });
      
      r.on(RoomEvent.ParticipantDisconnected, (participant) => {
        console.log('[LK] Participant disconnected:', participant.identity);
      });
      
      r.on(RoomEvent.TrackPublished, (publication, participant) => {
        console.log('[LK] Track published:', publication.kind, 'by', participant.identity);
      });

      console.log('[frontend] connecting to room...');
      await r.connect(url, token);
      console.log('[frontend] ✅ Connected successfully!');
      
      // Log current participants
      console.log('[frontend] Current participants:', r.remoteParticipants.size);
      r.remoteParticipants.forEach((p) => {
        console.log('[frontend] Remote participant:', p.identity);
      });

      // publish mic
      const mic = await createLocalAudioTrack();
      await r.localParticipant.publishTrack(mic);
      console.log('[frontend] ✅ Microphone published');

      // attach already-subscribed remote audio
      if (r.remoteParticipants) {
        r.remoteParticipants.forEach((p: RemoteParticipant) => {
          if (p && p.trackPublications) {
            p.trackPublications.forEach((pub: RemoteTrackPublication) => {
              if (pub.kind === Track.Kind.Audio && pub.isSubscribed && pub.audioTrack) {
                attachRemoteAudio(p, pub);
              }
            });
          }
        });
      }

      // Try to trigger agent to join (if you have this endpoint)
      const triggerAgent = async () => {
        try {
          console.log('[frontend] Triggering agent to join...');
          const agentTriggerUrl = `${SERVER_BASE}/trigger-agent?room=${encodeURIComponent(roomName)}`;
          const agentResp = await fetch(agentTriggerUrl, { 
            method: 'POST',
            credentials: 'include' 
          });
          if (agentResp.ok) {
            console.log('[frontend] Agent trigger successful');
          } else {
            console.warn('[frontend] Agent trigger failed:', agentResp.status);
          }
        } catch (e) {
          console.warn('[frontend] Agent trigger error (might not be implemented):', e);
        }
      };
      
      // Trigger agent
      await triggerAgent();

      // Wait for agent, then start STT
      console.log('[frontend] Waiting for agent to join...');
      setTimeout(() => {
        console.log('[frontend] Current participants after wait:', r.remoteParticipants.size);
        
        if (r.remoteParticipants.size === 0) {
          console.log('[frontend] No agent joined, starting STT anyway...');
          setSttStatus('⚠️ No agent detected, but starting speech recognition...');
        } else {
          console.log('[frontend] Agent detected, starting STT...');
          setSttStatus('🤖 Agent present, starting speech recognition...');
        }
        
        // Start browser STT
        console.log('[frontend] Starting browser STT...');
        startBrowserSTT();
      }, 3000); // Wait 3 seconds for agent to join

      // Store room reference for debugging
      (window as any).lkRoom = r;

      setIdentity(ident || me);
      setRoom(r);
      setConnected(true);
      setSttStatus('🤖 Waiting for agent to join...');
      console.log('[frontend] Call setup complete!');
    } catch (e: any) {
      console.error('Start call failed:', e);
      
      // Clean up any partial state
      setConnected(false);
      setRoom(null);
      setTranscript([]);
      setSttStatus('');
      setSttActive(false);
      setIdentity('');
      shouldRestartRef.current = false;
      partialIdRef.current = null;
      
      // Clear window reference if it exists
      if ((window as any).lkRoom) {
        delete (window as any).lkRoom;
      }
      
      if (e.name === 'NotAllowedError') {
        alert('Microphone permission denied. Please allow microphone access and try again.');
      } else {
        alert(`Could not start call.\n${e?.message ?? e}`);
      }
      stopBrowserSTT();
    } finally {
      setConnecting(false);
    }
  }, [
    roomName,
    onTrackSubscribed,
    handleTranscription,
    attachRemoteAudio,
    startBrowserSTT,
    stopBrowserSTT,
  ]);

  const endCall = useCallback(async () => {
    try {
      console.log('[frontend] Ending call...');
      stopBrowserSTT();
      if (room) {
        console.log('[frontend] Disconnecting from room...');
        await room.disconnect();
      }
    } catch (e) {
      console.error('[frontend] Error during call end:', e);
    } finally {
      console.log('[frontend] Resetting state...');
      setConnected(false);
      setRoom(null);
      setTranscript([]);
      setSttStatus('');
      setSttActive(false);
      setIdentity('');
      shouldRestartRef.current = false;
      partialIdRef.current = null;
      
      // Clean up window reference
      if ((window as any).lkRoom) {
        delete (window as any).lkRoom;
        console.log('[frontend] Cleared window.lkRoom reference');
      }
    }
  }, [room, stopBrowserSTT]);

  // PDF upload handler
  const onUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    setUploading(true);
    setUploadStatus('📤 Uploading PDF...');
    
    const fd = new FormData();
    fd.append('file', file);
    
    try {
      const res = await fetch(`${UPLOAD_SERVER}/upload`, { 
        method: 'POST', 
        body: fd 
      });
      
      if (!res.ok) {
        const errorText = await res.text();
        throw new Error(errorText || 'Upload failed');
      }
      
      const result = await res.json();
      setUploadStatus(`✅ ${result.message}`);
      
      // Refresh vectorstore info
      await fetchVectorstoreInfo();
      
      // Clear status after 3 seconds
      setTimeout(() => setUploadStatus(''), 3000);
    } catch (err: any) {
      console.error('Upload error:', err);
      setUploadStatus(`❌ Upload failed: ${err?.message ?? err}`);
      setTimeout(() => setUploadStatus(''), 5000);
    } finally {
      setUploading(false);
      e.currentTarget.value = '';
    }
  }, []);

  return (
    <div className="h-full min-h-screen bg-neutral-50 text-neutral-900 flex flex-col items-center">
      <div className="w-full max-w-4xl px-4 py-6">
        <h1 className="text-3xl font-bold text-neutral-900">
          🍳 KitchenCompanion
        </h1>
        <p className="text-sm text-neutral-600 mt-1">
          Voice-powered cooking assistant with PDF cookbook RAG
        </p>

        {/* Vectorstore Status */}
        {vectorstoreInfo && (
          <div className={`mt-4 p-3 rounded-lg border ${
            vectorstoreInfo.status === 'ready' 
              ? 'bg-emerald-50 border-emerald-300 text-emerald-800'
              : vectorstoreInfo.status === 'empty'
              ? 'bg-amber-50 border-amber-300 text-amber-800'
              : 'bg-neutral-100 border-neutral-300 text-neutral-700'
          }`}>
            <div className="flex items-center justify-between">
              <div>
                <div className="font-semibold">
                  {vectorstoreInfo.status === 'ready' ? '✅ Knowledge Base Ready' :
                   vectorstoreInfo.status === 'empty' ? '📚 No PDFs Uploaded Yet' :
                   '⚠️ Knowledge Base Status Unknown'}
                </div>
                <div className="text-sm mt-1">
                  {vectorstoreInfo.pdf_count ? `${vectorstoreInfo.pdf_count} PDF(s) loaded` : 'Upload a PDF to get started'}
                  {vectorstoreInfo.vector_count && ` • ${vectorstoreInfo.vector_count} knowledge chunks`}
                </div>
                {vectorstoreInfo.uploaded_pdfs && vectorstoreInfo.uploaded_pdfs.length > 0 && (
                  <div className="text-xs mt-1 opacity-75">
                    PDFs: {vectorstoreInfo.uploaded_pdfs.join(', ')}
                  </div>
                )}
              </div>
              <button
                onClick={fetchVectorstoreInfo}
                className="px-3 py-1 text-xs rounded bg-white hover:bg-neutral-100 border border-neutral-300 transition-colors"
              >
                Refresh
              </button>
            </div>
          </div>
        )}

        {/* Upload Section */}
        <div className="mt-4 p-4 rounded-lg bg-white border border-neutral-300">
          <div className="flex items-center justify-between gap-4">
            <div className="flex-1">
              <h3 className="font-semibold text-sm">Upload Cookbook PDF</h3>
              <p className="text-xs text-neutral-600 mt-1">
                Add cooking knowledge that the agent can reference during conversations
              </p>
            </div>
            <label className={`px-4 py-2 rounded font-medium cursor-pointer transition-colors whitespace-nowrap ${
              uploading 
                ? 'bg-neutral-300 text-neutral-600 cursor-not-allowed'
                : 'bg-blue-600 text-white hover:bg-blue-700'
            }`}>
              <input 
                type="file" 
                className="hidden" 
                accept="application/pdf" 
                onChange={onUpload}
                disabled={uploading}
              />
              {uploading ? 'Uploading...' : '📄 Upload PDF'}
            </label>
          </div>
          {uploadStatus && (
            <div className="mt-2 text-sm p-2 rounded bg-neutral-100">
              {uploadStatus}
            </div>
          )}
        </div>

        {/* Call Controls */}
        <div className="mt-4 p-4 rounded-lg bg-white border border-neutral-300">
          <div className="flex gap-2 items-center flex-wrap">
            <label className="text-sm font-medium">Room:</label>
            <input
              className="px-3 py-2 rounded border border-neutral-300 flex-1 min-w-[200px]"
              value={roomName}
              onChange={(e) => setRoomName(e.target.value)}
              disabled={connected}
            />
            <button
              className="px-6 py-2 rounded font-medium bg-emerald-600 text-white hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              onClick={startCall}
              disabled={connecting || connected}
            >
              {connecting ? '🔄 Connecting...' : '🎙️ Start Call'}
            </button>
            <button
              className="px-6 py-2 rounded font-medium bg-rose-600 text-white hover:bg-rose-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              onClick={endCall}
              disabled={!connected}
            >
              ⏹️ End Call
            </button>
          </div>

          {sttStatus && (
            <div className={`mt-3 text-sm p-2 rounded border ${
              sttActive 
                ? 'bg-emerald-50 text-emerald-700 border-emerald-200' 
                : 'bg-neutral-100 text-neutral-600 border-neutral-200'
            }`}>
              {sttStatus}
            </div>
          )}
        </div>

        {/* Transcript */}
        <div className="mt-4">
          <h2 className="text-lg font-semibold mb-2">Live Transcript</h2>
          <div
            ref={scrollRef}
            className="h-[50vh] overflow-auto rounded-lg border border-neutral-300 bg-white p-4"
          >
            {transcript.length === 0 && (
              <div className="text-neutral-500 text-sm">
                {connected 
                  ? '🎤 Start speaking... Your speech will appear here.'
                  : '👋 Click "Start Call" to begin. Upload a PDF first to give the agent cooking knowledge!'}
              </div>
            )}
            {transcript.map((line) => (
              <div key={line.id} className="mb-3 leading-relaxed">
                <span className={`font-semibold ${
                  line.participant === 'Transcript' 
                    ? 'text-blue-700' 
                    : 'text-emerald-700'
                }`}>
                  {line.participant}:
                </span>{' '}
                <span className={line.isFinal ? 'opacity-100' : 'opacity-70 italic'}>
                  {line.text}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Hidden audio element for agent audio playback */}
        <audio ref={audioRef} autoPlay playsInline />
        
        {connected && (
          <div className="mt-3 text-xs text-neutral-600 flex items-center justify-between">
            <span>
              Connected as <span className="font-mono bg-neutral-100 px-2 py-1 rounded">{identity}</span>
            </span>
            {sttActive && (
              <span className="flex items-center gap-2">
                <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse"></span>
                Speech recognition active
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}