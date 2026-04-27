import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  QuizSession,
  QuizQuestion,
  type PipelineType,
} from "../api/client";
import FeedbackControls from "../components/FeedbackControls";
import PipelineStatusBanner from "../components/PipelineStatusBanner";
import RunPipelineButton from "../components/RunPipelineButton";
import { usePipelineStatus } from "../hooks/usePipelineStatus";

const QUIZ_PIPELINES: readonly PipelineType[] = [
  "quiz_generation",
  "quiz_evaluation",
];

export default function QuizPage() {
  const [sessions, setSessions] = useState<QuizSession[]>([]);
  const [current, setCurrent] = useState<
    (QuizSession & { questions: QuizQuestion[] }) | null
  >(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [refreshing, setRefreshing] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [reviewSession, setReviewSession] = useState<
    (QuizSession & { questions: QuizQuestion[] }) | null
  >(null);
  const pipelines = useMemo(() => QUIZ_PIPELINES, []);
  const status = usePipelineStatus(pipelines);

  const loadAll = useCallback(() => {
    return Promise.all([
      api.quiz
        .listSessions()
        .then(setSessions)
        .catch(() => {}),
      api.quiz
        .getCurrent()
        .then(setCurrent)
        .catch(() => setCurrent(null)),
    ]);
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await Promise.all([loadAll(), status.refresh()]);
    } finally {
      setRefreshing(false);
    }
  }, [loadAll, status]);

  const submitAnswer = async (qId: string) => {
    const text = answers[qId];
    if (!text) return;
    await api.quiz.submitAnswer(qId, text);
    // Refresh
    if (current) {
      api.quiz.getSession(current.id).then(setCurrent);
    }
  };

  const openReview = async (sessionId: string) => {
    const detail = await api.quiz.getSession(sessionId);
    setEvaluating(false);
    setReviewSession(detail);
  };

  const completeSession = async () => {
    if (!current) return;
    const completedId = current.id;
    await api.quiz.completeSession(completedId);
    setCurrent(null);
    api.quiz.listSessions().then(setSessions);
    // Kick off LLM evaluation immediately (runs in background on the server)
    api.pipelines
      .runQuizEvaluation(completedId)
      .then(() => status.refresh())
      .catch(() => {}); // evaluation can be re-triggered manually from the review view
    // Show results immediately
    openReview(completedId);
  };

  // Shared question card renderer
  const renderQuestionCard = (
    q: QuizQuestion,
    i: number,
    readOnly: boolean,
  ) => (
    <div
      key={q.id}
      className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
    >
      <div className="mb-2 flex items-start justify-between gap-3">
        <div className="flex-1">
          <p className="font-medium">
            {i + 1}. {q.question_text}
          </p>
          {q.topic_name && (
            <span
              className="mt-2 inline-block rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700 ring-1 ring-inset ring-brand-200"
              title="Knowledge Profile topic this question targets"
            >
              {q.topic_name}
            </span>
          )}
        </div>
        <FeedbackControls targetType="quiz_question" targetId={q.id} />
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
          {q.reference_answer && (
            <details className="mt-2 border-t pt-2" open={!!q.evaluation}>
              <summary className="cursor-pointer text-xs font-semibold text-brand-700 hover:text-brand-800">
                Expected answer
              </summary>
              <p className="mt-1 whitespace-pre-line text-xs text-gray-700">
                {q.reference_answer}
              </p>
            </details>
          )}
        </div>
      ) : readOnly ? (
        <p className="mt-2 text-sm italic text-gray-400">No answer submitted</p>
      ) : (
        <div className="mt-2 flex gap-2">
          <textarea
            value={answers[q.id] ?? ""}
            onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })}
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
  );

  // Score summary for evaluated sessions
  const renderScoreSummary = (questions: QuizQuestion[]) => {
    const evaluated = questions.filter((q) => q.evaluation);
    if (evaluated.length === 0) return null;
    const full = evaluated.filter(
      (q) => q.evaluation!.correctness === "full",
    ).length;
    const partial = evaluated.filter(
      (q) => q.evaluation!.correctness === "partial",
    ).length;
    const incorrect = evaluated.length - full - partial;
    return (
      <div className="mb-4 flex gap-4 rounded-lg border border-gray-200 bg-white p-4">
        <div className="text-center">
          <div className="text-2xl font-bold text-green-700">{full}</div>
          <div className="text-xs text-gray-500">Correct</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold text-yellow-600">{partial}</div>
          <div className="text-xs text-gray-500">Partial</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold text-red-600">{incorrect}</div>
          <div className="text-xs text-gray-500">Incorrect</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold text-gray-700">
            {evaluated.length}
          </div>
          <div className="text-xs text-gray-500">Total</div>
        </div>
      </div>
    );
  };

  // Review view for a completed session
  if (reviewSession) {
    return (
      <div>
        <div className="mb-6 flex items-baseline gap-3">
          <button
            onClick={() => setReviewSession(null)}
            className="text-sm text-brand-600 hover:text-brand-800"
          >
            ← Back to Quiz
          </button>
          <h1 className="text-2xl font-bold">Quiz Results</h1>
          <span className="text-sm text-gray-400">
            {new Date(reviewSession.created_at).toLocaleDateString()} ·{" "}
            {reviewSession.question_count} questions · {reviewSession.status}
          </span>
        </div>

        {renderScoreSummary(reviewSession.questions)}

        {reviewSession.status !== "evaluated" && (
          <div className="mb-4 rounded-lg border border-yellow-200 bg-yellow-50 p-3 text-sm text-yellow-800">
            {status.running.some((r) => r === "quiz_evaluation") ? (
              <>Evaluation is running… Refresh to check for updates.</>
            ) : (
              <>Evaluations have not been generated yet.</>
            )}
            <button
              onClick={() => openReview(reviewSession.id)}
              className="ml-2 font-medium text-yellow-900 underline hover:no-underline"
            >
              Refresh
            </button>
            {!status.running.some((r) => r === "quiz_evaluation") && (
              <button
                disabled={evaluating}
                onClick={async () => {
                  if (evaluating) return;
                  setEvaluating(true);
                  try {
                    await api.pipelines.runQuizEvaluation(reviewSession.id);
                    await status.refresh();
                  } finally {
                    setEvaluating(false);
                  }
                }}
                className="ml-2 rounded bg-yellow-700 px-2 py-0.5 text-xs font-medium text-white hover:bg-yellow-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {evaluating ? "Queuing…" : "Evaluate now"}
              </button>
            )}
          </div>
        )}

        <div className="space-y-4">
          {reviewSession.questions.map((q, i) =>
            renderQuestionCard(q, i, true),
          )}
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6 flex items-baseline gap-3">
        <h1 className="text-2xl font-bold">Quiz</h1>
        <span className="text-sm text-gray-400">
          Test and reinforce your knowledge
        </span>
      </div>

      <PipelineStatusBanner
        label="quiz"
        running={status.running}
        runningSince={status.runningSince}
        lastCompletedAt={status.lastCompletedAt}
        loaded={status.loaded}
        onRefresh={handleRefresh}
        refreshing={refreshing}
      />

      {!current ? (
        <div>
          {status.running.length === 0 && (
            <div className="mb-4">
              <p className="mb-3 text-gray-500">No active quiz right now.</p>
              <RunPipelineButton
                label="Generate quiz now"
                onRun={() => api.pipelines.runQuizGeneration()}
                onQueued={() => status.refresh()}
                disabled={!status.loaded}
              />
            </div>
          )}
          {sessions.length > 0 && (
            <div>
              <h2 className="mb-2 text-lg font-semibold">Past Sessions</h2>
              <div className="space-y-2">
                {sessions.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => openReview(s.id)}
                    className="w-full cursor-pointer rounded border border-gray-200 bg-white p-3 text-left text-sm transition-colors hover:border-brand-300 hover:bg-brand-50"
                  >
                    <span className="font-medium">
                      {new Date(s.created_at).toLocaleDateString()}
                    </span>
                    <span className="ml-2 text-gray-500">
                      {s.question_count} questions · {s.status}
                    </span>
                  </button>
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
            {current.questions.map((q, i) => renderQuestionCard(q, i, false))}
          </div>
        </div>
      )}
    </div>
  );
}
