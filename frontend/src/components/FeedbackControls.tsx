import { ThumbsUp, ThumbsDown } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";

interface Props {
  targetType: string;
  targetId: string;
}

export default function FeedbackControls({ targetType, targetId }: Props) {
  const [reaction, setReaction] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [showNote, setShowNote] = useState(false);
  const [saved, setSaved] = useState(false);

  const submit = async (r: string | null) => {
    setReaction(r);
    await api.feedback.create({
      target_type: targetType,
      target_id: targetId,
      reaction: r ?? undefined,
      note: note || undefined,
    });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => submit("thumbs_up")}
        className={`rounded p-1 transition-colors ${
          reaction === "thumbs_up"
            ? "bg-green-50 text-green-600"
            : "text-gray-400 hover:text-green-600"
        }`}
        title="Helpful"
      >
        <ThumbsUp size={16} />
      </button>
      <button
        onClick={() => submit("thumbs_down")}
        className={`rounded p-1 transition-colors ${
          reaction === "thumbs_down"
            ? "bg-red-50 text-red-600"
            : "text-gray-400 hover:text-red-600"
        }`}
        title="Not helpful"
      >
        <ThumbsDown size={16} />
      </button>
      <button
        onClick={() => setShowNote(!showNote)}
        className="text-xs text-gray-400 hover:text-gray-600"
      >
        + note
      </button>
      {showNote && (
        <form
          className="flex items-center gap-1"
          onSubmit={(e) => {
            e.preventDefault();
            submit(reaction);
          }}
        >
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Feedforward note…"
            className="rounded border border-gray-300 px-2 py-1 text-xs"
          />
          <button
            type="submit"
            className="rounded bg-brand-600 px-2 py-1 text-xs text-white"
          >
            Save
          </button>
        </form>
      )}
      {saved && <span className="text-xs text-green-600">Saved</span>}
    </div>
  );
}
