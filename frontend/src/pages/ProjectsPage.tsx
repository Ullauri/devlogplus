import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  WeeklyProject,
  WeeklyProjectDetail,
  type PipelineType,
} from "../api/client";
import FeedbackControls from "../components/FeedbackControls";
import PipelineStatusBanner from "../components/PipelineStatusBanner";
import { usePipelineStatus } from "../hooks/usePipelineStatus";

const STATUS_COLOR: Record<string, string> = {
  issued: "bg-blue-100 text-blue-800",
  in_progress: "bg-yellow-100 text-yellow-800",
  submitted: "bg-purple-100 text-purple-800",
  evaluated: "bg-green-100 text-green-800",
};

const TASK_TYPE_COLOR: Record<string, string> = {
  bug_fix: "bg-red-100 text-red-700",
  feature: "bg-green-100 text-green-700",
  refactor: "bg-yellow-100 text-yellow-700",
  optimization: "bg-blue-100 text-blue-700",
};

const PROJECT_PIPELINES: readonly PipelineType[] = [
  "project_generation",
  "project_evaluation",
];

export default function ProjectsPage() {
  const [projects, setProjects] = useState<WeeklyProject[]>([]);
  const [current, setCurrent] = useState<WeeklyProjectDetail | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const pipelines = useMemo(() => PROJECT_PIPELINES, []);
  const status = usePipelineStatus(pipelines);

  const loadAll = useCallback(() => {
    return Promise.all([
      api.projects
        .list()
        .then(setProjects)
        .catch(() => {}),
      api.projects
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

  const submit = async () => {
    if (!current) return;
    await api.projects.submit(current.id);
    api.projects
      .getCurrent()
      .then(setCurrent)
      .catch(() => setCurrent(null));
    api.projects.list().then(setProjects);
  };

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">Weekly Projects</h1>

      <PipelineStatusBanner
        label="project"
        running={status.running}
        runningSince={status.runningSince}
        lastCompletedAt={status.lastCompletedAt}
        loaded={status.loaded}
        onRefresh={handleRefresh}
        refreshing={refreshing}
      />

      {current ? (
        <div className="mb-8 rounded-lg border-2 border-brand-200 bg-white p-5 shadow-sm">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold">{current.title}</h2>
              <span
                className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLOR[current.status] ?? "bg-gray-100"}`}
              >
                {current.status}
              </span>
              <span className="ml-2 text-xs text-gray-500">
                Difficulty: {current.difficulty_level}/5
              </span>
            </div>
            <FeedbackControls targetType="project" targetId={current.id} />
          </div>
          <p className="mb-4 text-sm text-gray-700">{current.description}</p>

          {current.tasks.length > 0 && (
            <div className="mb-4">
              <h3 className="mb-2 text-sm font-semibold">Tasks</h3>
              <div className="space-y-2">
                {current.tasks.map((task) => (
                  <div
                    key={task.id}
                    className="flex items-start gap-2 rounded bg-gray-50 p-2 text-sm"
                  >
                    <span
                      className={`mt-0.5 rounded-full px-2 py-0.5 text-xs font-medium ${TASK_TYPE_COLOR[task.task_type] ?? "bg-gray-100"}`}
                    >
                      {task.task_type}
                    </span>
                    <div className="flex-1">
                      <span className="font-medium">{task.title}</span>
                      <p className="text-xs text-gray-500">
                        {task.description}
                      </p>
                    </div>
                    <FeedbackControls
                      targetType="project_task"
                      targetId={task.id}
                    />
                  </div>
                ))}
              </div>
            </div>
          )}

          {(current.status === "issued" ||
            current.status === "in_progress") && (
            <button
              onClick={submit}
              className="rounded bg-green-600 px-4 py-2 text-sm text-white hover:bg-green-700"
            >
              Submit for Evaluation
            </button>
          )}
        </div>
      ) : (
        status.running.length === 0 && (
          <p className="mb-6 text-gray-500">
            No active project. A new project is issued weekly.
          </p>
        )
      )}

      {projects.length > 0 && (
        <div>
          <h2 className="mb-3 text-lg font-semibold">Past Projects</h2>
          <div className="space-y-2">
            {projects
              .filter((p) => p.id !== current?.id)
              .map((p) => (
                <div
                  key={p.id}
                  className="rounded border border-gray-200 bg-white p-3 text-sm"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{p.title}</span>
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLOR[p.status] ?? "bg-gray-100"}`}
                    >
                      {p.status}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-gray-500">{p.description}</p>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
