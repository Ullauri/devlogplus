import { Mic, MicOff } from "lucide-react";
import { useState, useRef, useCallback } from "react";

interface Props {
  onTranscript: (text: string) => void;
}

/** Browser Web Speech API dictation button — text only, no audio files. */
export default function SpeechInput({ onTranscript }: Props) {
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<SpeechRecognition | null>(null);

  const toggle = useCallback(() => {
    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      return;
    }

    const SpeechRecognition =
      window.SpeechRecognition ??
      (
        window as unknown as {
          webkitSpeechRecognition: typeof window.SpeechRecognition;
        }
      ).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Speech recognition not supported in this browser.");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = "en-US";

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      const transcript = Array.from(event.results)
        .map((r) => r[0]?.transcript ?? "")
        .join(" ");
      onTranscript(transcript);
    };

    recognition.onerror = () => setListening(false);
    recognition.onend = () => setListening(false);

    recognition.start();
    recognitionRef.current = recognition;
    setListening(true);
  }, [listening, onTranscript]);

  return (
    <button
      type="button"
      onClick={toggle}
      className={`rounded-full p-2 transition-colors ${
        listening
          ? "bg-red-100 text-red-600"
          : "bg-gray-100 text-gray-500 hover:bg-gray-200"
      }`}
      title={listening ? "Stop dictation" : "Start dictation"}
    >
      {listening ? <MicOff size={18} /> : <Mic size={18} />}
    </button>
  );
}
