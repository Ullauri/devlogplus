import { ThumbsUp, ThumbsDown } from "lucide-react";
import { useEffect, useState } from "react";
import type { components } from "../api/schema.gen";
import { api } from "../api/client";

type TargetType = components["schemas"]["FeedbackTargetType"];
type Reaction = components["schemas"]["FeedbackReaction"];

interface Props {
  targetType: TargetType;
  targetId: string;
}

/**
 * Thumbs-up / thumbs-down + feedforward note control.
 *
 * On mount, hydrates with the most recent persisted feedback for this
 * (targetType, targetId) so users see their previous rating and note
 * when a page is re-rendered. Clicking the currently-active reaction
 * again clears it.
 */
export default function FeedbackControls({ targetType, targetId }: Props) {
  const [reaction, setReaction] = useState<Reaction | null>(null);
  const [note, setNote] = useState("");
  const [showNote, setShowNote] = useState(false);
  const [saved, setSaved] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.feedback
      .listFor(targetType, targetId)
      .then((items) => {
        if (cancelled) return;
        // API returns most-recent first; take the latest reaction and
        // the latest non-empty note (may come from different rows).
        const latestReaction = items.find((f) => f.reaction)?.reaction ?? null;
        const latestNote = items.find((f) => f.note)?.note ?? "";
        setReaction(latestReaction);
        setNote(latestNote);
        if (latestNote) setShowNote(true);
      })
      .catch(() => {
        // Non-fatal: hydration is best-effort.
      })
      .finally(() => {
        if (!cancelled) setHydrated(true);
      });
    return () => {
      cancelled = true;
    };
  }, [targetType, targetId]);

  const submit = async (r: Reaction | null) => {
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

  // Clicking the same reaction again clears it.
  const toggleReaction = (r: Reaction) => submit(reaction === r ? null : r);

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => toggleReaction("thumbs_up")}
        className={`rounded p-1 transition-colors ${
          reaction === "thumbs_up"
            ? "bg-green-50 text-green-600"
            : "text-gray-400 hover:text-green-600"
        }`}
        title="Mark this as helpful — tells DevLog+ this content was useful so future suggestions lean this way. Click again to clear."
        aria-label="Mark this as helpful"
      >
        <ThumbsUp size={16} />
      </button>
      <button
        onClick={() => toggleReaction("thumbs_down")}
        className={`rounded p-1 transition-colors ${
          reaction === "thumbs_down"
            ? "bg-red-50 text-red-600"
            : "text-gray-400 hover:text-red-600"
        }`}
        title="Mark this as not helpful — tells DevLog+ to avoid similar suggestions in the future. Click again to clear."
        aria-label="Mark this as not helpful"
      >
        <ThumbsDown size={16} />
      </button>
      <button
        onClick={() => setShowNote(!showNote)}
        className="text-xs text-gray-400 hover:text-gray-600"
        title={
          note
            ? "Edit your feedforward note — change the written context that shapes future AI suggestions for this item."
            : "Add a feedforward note — write a short comment (e.g. 'too easy', 'wrong topic') that DevLog+ uses to tailor future suggestions."
        }
      >
        {note ? "edit note" : "+ note"}
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
            title="Save your feedforward note so it's recorded with this feedback."
          >
            Save
          </button>
        </form>
      )}
      {saved && <span className="text-xs text-green-600">Saved</span>}
      {!hydrated && (
        <span className="sr-only" aria-live="polite">
          Loading feedback…
        </span>
      )}
    </div>
  );
}
