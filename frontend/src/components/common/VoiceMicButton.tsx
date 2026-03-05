import React, { useState, useRef, useCallback } from 'react';
import { Mic } from 'lucide-react';
import { apiClient } from '../../api/client';

interface VoiceMicButtonProps {
  onTranscribe: (text: string) => void;
  disabled?: boolean;
  className?: string;
}

type RecordingState = 'idle' | 'recording' | 'transcribing';

const VoiceMicButton: React.FC<VoiceMicButtonProps> = ({
  onTranscribe,
  disabled = false,
  className = '',
}) => {
  const [state, setState] = useState<RecordingState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);

  const stopStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
  }, []);

  const sendAudioForTranscription = useCallback(
    async (audioBlob: Blob) => {
      setState('transcribing');
      setError(null);

      try {
        const formData = new FormData();
        formData.append('file', audioBlob, 'recording.webm');

        const response = await apiClient.post('/api/speech/transcribe', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
          timeout: 60000,
        });

        const text = response.data?.text;
        if (text) {
          onTranscribe(text);
        } else {
          setError('No speech detected.');
        }
      } catch (err: unknown) {
        const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } };
        const detail = axiosErr.response?.data?.detail;
        if (axiosErr.response?.status === 503) {
          setError('Voice input not configured.');
        } else if (axiosErr.response?.status === 502) {
          setError('Transcription service error.');
        } else {
          setError(detail || 'Transcription failed.');
        }
      } finally {
        setState('idle');
      }
    },
    [onTranscribe],
  );

  const startRecording = useCallback(async () => {
    setError(null);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // Determine supported MIME type
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm')
          ? 'audio/webm'
          : '';

      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);

      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      recorder.onstop = () => {
        stopStream();
        const blob = new Blob(chunksRef.current, {
          type: recorder.mimeType || 'audio/webm',
        });
        chunksRef.current = [];

        if (blob.size > 0) {
          sendAudioForTranscription(blob);
        } else {
          setError('No audio recorded.');
          setState('idle');
        }
      };

      recorder.onerror = () => {
        stopStream();
        setError('Recording error.');
        setState('idle');
      };

      mediaRecorderRef.current = recorder;
      recorder.start();
      setState('recording');
      setPermissionDenied(false);
    } catch (err: unknown) {
      stopStream();
      const domErr = err as { name?: string };
      if (domErr.name === 'NotAllowedError' || domErr.name === 'PermissionDeniedError') {
        setPermissionDenied(true);
        setError('Microphone access denied. Please allow microphone permission.');
      } else if (domErr.name === 'NotFoundError') {
        setError('No microphone found.');
      } else {
        setError('Could not start recording.');
      }
      setState('idle');
    }
  }, [stopStream, sendAudioForTranscription]);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
  }, []);

  const handleClick = useCallback(() => {
    if (state === 'recording') {
      stopRecording();
    } else if (state === 'idle') {
      startRecording();
    }
    // Do nothing while transcribing
  }, [state, startRecording, stopRecording]);

  const isDisabled = disabled || permissionDenied || state === 'transcribing';

  return (
    <div className={`relative inline-flex items-center ${className}`}>
      <button
        type="button"
        onClick={handleClick}
        disabled={isDisabled}
        className={`relative w-8 h-8 flex items-center justify-center rounded-lg transition-all ${
          state === 'recording'
            ? 'bg-red-500 text-white hover:bg-red-600 animate-pulse'
            : state === 'transcribing'
              ? 'bg-slate-200 text-slate-400 cursor-wait'
              : permissionDenied
                ? 'bg-slate-100 text-slate-300 cursor-not-allowed'
                : 'bg-slate-100 text-slate-500 hover:bg-slate-200 hover:text-slate-700'
        }`}
        title={
          state === 'recording'
            ? 'Stop recording'
            : state === 'transcribing'
              ? 'Transcribing...'
              : permissionDenied
                ? 'Microphone access denied'
                : 'Start voice input'
        }
      >
        {state === 'transcribing' ? (
          <div className="w-4 h-4 border-2 border-slate-400 border-t-transparent rounded-full animate-spin" />
        ) : (
          <Mic size={16} />
        )}
        {state === 'recording' && (
          <span className="absolute -top-1 -right-1 w-3 h-3 bg-red-500 rounded-full animate-ping" />
        )}
      </button>
      {error && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-1.5 bg-red-50 border border-red-200 rounded-lg text-[10px] text-red-600 font-medium whitespace-nowrap z-50 shadow-sm">
          {error}
          <button
            type="button"
            onClick={() => setError(null)}
            className="ml-2 text-red-400 hover:text-red-600"
          >
            ✕
          </button>
        </div>
      )}
    </div>
  );
};

export default VoiceMicButton;