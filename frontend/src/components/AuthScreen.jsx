export default function AuthScreen({
    mode,
    form,
    loading,
    error,
    onFieldChange,
    onModeChange,
    onSubmit,
}) {
    return (
        <div className="min-h-screen bg-[#0a0c10] text-gray-100 px-4 py-10">
            <div className="mx-auto flex min-h-[calc(100vh-5rem)] max-w-6xl items-center justify-center">
                <div className="grid w-full overflow-hidden rounded-[2rem] border border-white/10 bg-[#101318] shadow-[0_30px_80px_rgba(0,0,0,0.45)] lg:grid-cols-[1.15fr_0.85fr]">
                    <section className="relative overflow-hidden border-b border-white/10 bg-[radial-gradient(circle_at_top_left,_rgba(59,130,246,0.18),_transparent_40%),linear-gradient(180deg,_rgba(255,255,255,0.04),_rgba(255,255,255,0))] p-8 sm:p-12 lg:border-b-0 lg:border-r">
                        <div className="absolute inset-y-0 right-0 hidden w-px bg-white/10 lg:block" />
                        <div className="max-w-xl space-y-6">
                            <span className="inline-flex items-center rounded-full border border-blue-400/20 bg-blue-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.25em] text-blue-200">
                                Personal Workspace
                            </span>
                            <div className="space-y-4">
                                <h1 className="text-4xl font-black tracking-tight text-white sm:text-5xl">
                                    SAMSA Auditor
                                </h1>
                                <p className="max-w-lg text-base leading-7 text-gray-300 sm:text-lg">
                                    Sign in to keep your audits, reopen previous documents, and track your past usage
                                    from a persistent sidebar.
                                </p>
                            </div>
                            <div className="grid gap-4 sm:grid-cols-3">
                                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                                    <div className="text-sm font-semibold text-white">Private login</div>
                                    <p className="mt-2 text-sm text-gray-400">Simple username and password auth backed by the API.</p>
                                </div>
                                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                                    <div className="text-sm font-semibold text-white">Saved audits</div>
                                    <p className="mt-2 text-sm text-gray-400">Each completed audit is stored so you can reopen it later.</p>
                                </div>
                                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                                    <div className="text-sm font-semibold text-white">Fast restart</div>
                                    <p className="mt-2 text-sm text-gray-400">Your history stays available after restarts of the local app.</p>
                                </div>
                            </div>
                        </div>
                    </section>

                    <section className="p-8 sm:p-12">
                        <div className="mx-auto max-w-md space-y-6">
                            <div className="flex rounded-2xl border border-white/10 bg-[#161b22] p-1">
                                <button
                                    type="button"
                                    onClick={() => onModeChange("login")}
                                    className={`flex-1 rounded-xl px-4 py-3 text-sm font-semibold transition ${
                                        mode === "login" ? "bg-white text-[#111318]" : "text-gray-400 hover:text-white"
                                    }`}
                                >
                                    Sign in
                                </button>
                                <button
                                    type="button"
                                    onClick={() => onModeChange("register")}
                                    className={`flex-1 rounded-xl px-4 py-3 text-sm font-semibold transition ${
                                        mode === "register" ? "bg-white text-[#111318]" : "text-gray-400 hover:text-white"
                                    }`}
                                >
                                    Create account
                                </button>
                            </div>

                            <div className="space-y-2">
                                <h2 className="text-2xl font-bold text-white">
                                    {mode === "login" ? "Welcome back" : "Create your workspace"}
                                </h2>
                                <p className="text-sm leading-6 text-gray-400">
                                    {mode === "login"
                                        ? "Use your saved credentials to continue where you left off."
                                        : "Pick a username and password to start saving your audit history."}
                                </p>
                            </div>

                            <form className="space-y-4" onSubmit={onSubmit}>
                                <label className="block space-y-2">
                                    <span className="text-sm font-medium text-gray-300">Username</span>
                                    <input
                                        type="text"
                                        name="username"
                                        value={form.username}
                                        onChange={onFieldChange}
                                        autoComplete="username"
                                        className="w-full rounded-2xl border border-white/10 bg-[#0f1318] px-4 py-3 text-white outline-none transition focus:border-blue-400/60 focus:ring-2 focus:ring-blue-500/20"
                                        placeholder="Choose a username"
                                    />
                                </label>

                                <label className="block space-y-2">
                                    <span className="text-sm font-medium text-gray-300">Password</span>
                                    <input
                                        type="password"
                                        name="password"
                                        value={form.password}
                                        onChange={onFieldChange}
                                        autoComplete={mode === "login" ? "current-password" : "new-password"}
                                        className="w-full rounded-2xl border border-white/10 bg-[#0f1318] px-4 py-3 text-white outline-none transition focus:border-blue-400/60 focus:ring-2 focus:ring-blue-500/20"
                                        placeholder="Enter a password"
                                    />
                                </label>

                                {error ? (
                                    <div className="rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">
                                        {error}
                                    </div>
                                ) : null}

                                <button
                                    type="submit"
                                    disabled={loading}
                                    className="w-full rounded-2xl bg-blue-600 px-4 py-3 text-sm font-bold text-white transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-gray-700"
                                >
                                    {loading ? "Please wait..." : mode === "login" ? "Sign in" : "Create account"}
                                </button>
                            </form>
                        </div>
                    </section>
                </div>
            </div>
        </div>
    );
}
