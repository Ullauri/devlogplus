export default function SettingsPage() {
  // TODO: wire up saved state for settings persistence

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">Settings</h1>

      <div className="space-y-6">
        <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="mb-3 text-lg font-semibold">General</h2>
          <p className="text-sm text-gray-500">
            Settings are stored in the database and can be modified here. Most
            configuration (API keys, model selection, etc.) is managed via
            environment variables in{" "}
            <code className="rounded bg-gray-100 px-1 text-xs">.env</code>.
          </p>
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="mb-3 text-lg font-semibold">Scheduling</h2>
          <div className="space-y-2 text-sm text-gray-700">
            <p>
              📅 <strong>Nightly</strong>: Profile update — processes new
              journal entries (2:00 AM)
            </p>
            <p>
              📅 <strong>Weekly</strong>: Quiz generation (Monday 3:00 AM)
            </p>
            <p>
              📅 <strong>Weekly</strong>: Reading recommendations (Monday 3:30
              AM)
            </p>
            <p>
              📅 <strong>Weekly</strong>: Project generation (Monday 4:00 AM)
            </p>
          </div>
          <p className="mt-3 text-xs text-gray-500">
            Run{" "}
            <code className="rounded bg-gray-100 px-1">
              scripts/setup_cron.sh
            </code>{" "}
            to install crontab entries.
          </p>
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="mb-3 text-lg font-semibold">About</h2>
          <p className="text-sm text-gray-600">
            <strong>DevLog+</strong> — A single-user, locally-run developer
            journal for technical learning and skill maintenance. Powered by
            LLMs via OpenRouter with Langfuse observability.
          </p>
        </div>
      </div>
    </div>
  );
}
