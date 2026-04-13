import { useEffect, useState } from "react";
import { api, QuizSession, QuizQuestion } from "../api/client";
import FeedbackControls from "../components/FeedbackControls";

export default function QuizPage() {
  const [sessions, setSessions] = useState<QuizSession[]>([]);
  const [current, setCurrent] = useState<
    (QuizSession & { questions: QuizQuestion[] }) | null
  >(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});

  useEffect(() => {
    api.quiz
      .listSessions()
      .then(setSessions)
      .catch(() => {});
    api.quiz
      .getCurrent()
      .then(setCurrent)
      .catch(() => setCurrent(null));
  }, []);

  const submitAnswer = async (qId: string) => {
    const text = answers[qId];
    if (!text) return;
    await api.quiz.submitAnswer(qId, text);
    // Refresh
    if (current) {
      api.quiz.getSession(current.id).then(setCurrent);
    }
  };

  const completeSession = async () => {
    if (!current) return;
    await api.quiz.completeSession(current.id);
    api.quiz
      .getCurrent()
      .then(setCurrent)
      .catch(() => setCurrent(null));
    api.quiz.listSessions().then(setSessions);
  };

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">Quiz</h1>

      {!current ? (
        <div>
          <p className="mb-4 text-gray-500">
            No active quiz. A new quiz is generated weekly.
          </p>
          {sessions.length > 0 && (
            <div>
              <h2 className="mb-2 text-lg font-semibold">Past Sessions</h2>
              <div className="space-y-2">
                {sessions.map((s) => (
                  <div
                    key={s.id}
                    className="rounded border border-gray-200 bg-white p-3 text-sm"
                  >
                    <span className="font-medium">
                      {new Date(s.created_at).toLocaleDateString()}
                    </span>
                    <span className="ml-2 text-gray-500">
                      {s.question_count} questions · {s.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div>
          <div className="mb-4 flex items-center justify-between">
            <span className="text-sm text-gray-500">
              Status: <span className="font-medium">{current.status}</span> ·{" "}
              {current.question_count} questions
            </span>
            {current.status === "in_progress" && (
              <button
                onClick={completeSession}
                className="rounded bg-green-600 px-4 py-2 text-sm text-white hover:bg-green-700"
              >
                Complete Quiz
              </button>
            )}
          </div>

          <div className="space-y-4">
            {current.questions.map((q, i) => (
              <div
                key={q.id}
                className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
              >
                <div className="mb-2 flex items-start justify-between">
                  <p className="font-medium">
                    {i + 1}. {q.question_text}
                  </p>
                  <FeedbackControls
                    targetType="quiz_question"
                    targetId={q.id}
                  />
                </div>

                {q.answer ? (
                  <div className="mt-2 rounded bg-gray-50 p-3 text-sm">
                    <p className="text-gray-700">{q.answer.answer_text}</p>
                    {q.evaluation && (
                      <div className="mt-2 border-t pt-2">
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                            q.evaluation.correctness === "full"
                              ? "bg-green-100 text-green-800"
                              : q.evaluation.correctness === "partial"
                                ? "bg-yellow-100 text-yellow-800"
                                : "bg-red-100 text-red-800"
                          }`}
                        >
                          {q.evaluation.correctness}
                        </span>
                        <p className="mt-1 text-xs text-gray-600">
                          {q.evaluation.explanation}
                        </p>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="mt-2 flex gap-2">
                    <textarea
                      value={answers[q.id] ?? ""}
                      onChange={(e) =>
                        setAnswers({ ...answers, [q.id]: e.target.value })
                      }
                      placeholder="Your answer…"
                      rows={3}
                      className="flex-1 rounded border border-gray-300 px-3 py-2 text-sm"
                    />
                    <button
                      onClick={() => submitAnswer(q.id)}
                      className="self-end rounded bg-brand-600 px-3 py-2 text-sm text-white hover:bg-brand-700"
                    >
                      Submit
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
