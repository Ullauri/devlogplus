import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { api, JournalEntry } from "../api/client";
import SpeechInput from "../components/SpeechInput";

export default function JournalPage() {
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);

  const load = () => api.journal.list().then(setEntries);

  useEffect(() => {
    load();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (editingId) {
      await api.journal.update(editingId, {
        title: title || undefined,
        content,
      });
    } else {
      await api.journal.create({ title: title || undefined, content });
    }
    setTitle("");
    setContent("");
    setEditingId(null);
    setShowForm(false);
    load();
  };

  const startEdit = (entry: JournalEntry) => {
    setEditingId(entry.id);
    setTitle(entry.title ?? "");
    setContent(entry.current_content ?? "");
    setShowForm(true);
  };

  const handleDelete = async (id: string) => {
    if (confirm("Delete this entry?")) {
      await api.journal.delete(id);
      load();
    }
  };

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Journal</h1>
        <button
          onClick={() => {
            setShowForm(true);
            setEditingId(null);
            setTitle("");
            setContent("");
          }}
          className="flex items-center gap-1 rounded-md bg-brand-600 px-3 py-2 text-sm text-white hover:bg-brand-700"
        >
          <Plus size={16} /> New Entry
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={handleSubmit}
          className="mb-8 rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
        >
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Title (optional)"
            className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
          />
          <div className="mb-3 flex items-start gap-2">
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="What did you learn today? Something that confused you, or a topic you want to explore?"
              rows={6}
              className="flex-1 rounded border border-gray-300 px-3 py-2 text-sm"
              required
            />
            <SpeechInput
              onTranscript={(text) => setContent((prev) => prev + " " + text)}
            />
          </div>
          <div className="flex gap-2">
            <button
              type="submit"
              className="rounded bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700"
            >
              {editingId ? "Update" : "Save"}
            </button>
            <button
              type="button"
              onClick={() => {
                setShowForm(false);
                setEditingId(null);
              }}
              className="rounded border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {entries.length === 0 ? (
        <p className="text-gray-500">No journal entries yet. Start writing!</p>
      ) : (
        <div className="space-y-3">
          {entries.map((entry) => (
            <div
              key={entry.id}
              className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
            >
              <div className="mb-2 flex items-start justify-between">
                <div>
                  {entry.title && (
                    <h3 className="font-semibold">{entry.title}</h3>
                  )}
                  <span className="text-xs text-gray-400">
                    {new Date(entry.created_at).toLocaleDateString()}
                    {entry.is_processed && " · ✅ Processed"}
                  </span>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => startEdit(entry)}
                    className="text-xs text-brand-600 hover:underline"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleDelete(entry.id)}
                    className="text-xs text-red-500 hover:underline"
                  >
                    Delete
                  </button>
                </div>
              </div>
              <p className="whitespace-pre-wrap text-sm text-gray-700">
                {entry.current_content}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
