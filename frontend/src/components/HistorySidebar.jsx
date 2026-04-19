function formatDate(value) {
    try {
        return new Intl.DateTimeFormat(undefined, {
            month: "short",
            day: "numeric",
            hour: "numeric",
            minute: "2-digit",
        }).format(new Date(value));
    } catch {
        return value;
    }
}

export default function HistorySidebar({
    user,
    history,
    activeHistoryId,
    loadingHistory,
    onNewAudit,
    onSelectHistory,
    onLogout,
}) {
    return (
        <aside className="flex h-screen flex-col border-r border-white/10 bg-[#111318] text-gray-100">
            <div className="border-b border-white/10 p-4">
                <button
                    type="button"
                    onClick={onNewAudit}
                    className="flex w-full items-center justify-center rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-semibold text-white transition hover:bg-white/10"
                >
                    New audit
                </button>
            </div>

            <div className="px-4 pt-4">
                <div className="text-xs font-semibold uppercase tracking-[0.25em] text-gray-500">Audit history</div>
            </div>

            <div className="flex-1 overflow-y-auto px-3 pb-4 pt-3">
                {loadingHistory ? (
                    <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-gray-400">
                        Loading history...
                    </div>
                ) : history.length === 0 ? (
                    <div className="rounded-2xl border border-dashed border-white/10 bg-white/5 px-4 py-4 text-sm leading-6 text-gray-400">
                        Your completed audits will appear here once you run them.
                    </div>
                ) : (
                    <div className="space-y-2">
                        {history.map((item) => {
                            const active = item.id === activeHistoryId;
                            return (
                                <button
                                    key={item.id}
                                    type="button"
                                    onClick={() => onSelectHistory(item.id)}
                                    className={`w-full rounded-2xl border px-3 py-3 text-left transition ${
                                        active
                                            ? "border-blue-400/40 bg-blue-500/10"
                                            : "border-transparent bg-white/[0.03] hover:border-white/10 hover:bg-white/[0.06]"
                                    }`}
                                >
                                    <div className="max-h-11 overflow-hidden text-sm font-semibold leading-5 text-white">{item.title}</div>
                                    <div className="mt-2 max-h-10 overflow-hidden text-xs leading-5 text-gray-400">{item.preview}</div>
                                    <div className="mt-3 flex items-center justify-between text-[11px] uppercase tracking-[0.18em] text-gray-500">
                                        <span>{item.total} claims</span>
                                        <span>{formatDate(item.created_at)}</span>
                                    </div>
                                </button>
                            );
                        })}
                    </div>
                )}
            </div>

            <div className="border-t border-white/10 p-4">
                <div className="mb-3 rounded-2xl bg-white/5 px-4 py-3">
                    <div className="text-sm font-semibold text-white">{user.username}</div>
                    <div className="text-xs text-gray-400">Signed in workspace</div>
                </div>
                <button
                    type="button"
                    onClick={onLogout}
                    className="w-full rounded-2xl border border-white/10 px-4 py-3 text-sm font-semibold text-gray-300 transition hover:bg-white/10 hover:text-white"
                >
                    Log out
                </button>
            </div>
        </aside>
    );
}
