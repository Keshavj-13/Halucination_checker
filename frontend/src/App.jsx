import { useEffect, useRef, useState } from "react";
import {
    extractTextFromDocument,
    getCurrentUser,
    getHistoryDetail,
    listHistory,
    loadSample,
    login,
    logout,
    register,
    runAuditStream,
} from "./api";
import AuthScreen from "./components/AuthScreen";
import Summary from "./components/Summary";
import DocumentViewer from "./components/DocumentViewer";
import DetailPanel from "./components/DetailPanel";
import HistorySidebar from "./components/HistorySidebar";

const TOKEN_KEY = "samsa.auth.token";
const EMPTY_AUDIT = {
    claims: [],
    total: 0,
    verified: 0,
    plausible: 0,
    hallucinations: 0,
};

function App() {
    const fileInputRef = useRef(null);
    const streamAbortRef = useRef(null);
    const [document, setDocument] = useState("");
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [status, setStatus] = useState("");
    const [selectedClaim, setSelectedClaim] = useState(null);
    const [isDragOver, setIsDragOver] = useState(false);
    const [workspaceError, setWorkspaceError] = useState("");
    const [extractedFile, setExtractedFile] = useState(null);

    const [token, setToken] = useState(() => window.localStorage.getItem(TOKEN_KEY) ?? "");
    const [user, setUser] = useState(null);
    const [history, setHistory] = useState([]);
    const [loadingHistory, setLoadingHistory] = useState(false);
    const [activeHistoryId, setActiveHistoryId] = useState(null);
    const [authReady, setAuthReady] = useState(false);
    const [authMode, setAuthMode] = useState("login");
    const [authForm, setAuthForm] = useState({ username: "", password: "" });
    const [authLoading, setAuthLoading] = useState(false);
    const [authError, setAuthError] = useState("");

    useEffect(() => {
        let cancelled = false;

        async function restoreSession() {
            if (!token) {
                if (!cancelled) {
                    setUser(null);
                    setHistory([]);
                    setActiveHistoryId(null);
                    setAuthReady(true);
                    setLoadingHistory(false);
                }
                return;
            }

            if (!cancelled) {
                setAuthReady(false);
                setLoadingHistory(true);
            }

            try {
                const currentUser = await getCurrentUser(token);
                if (cancelled) {
                    return;
                }

                setUser(currentUser);
                setAuthError("");

                const items = await listHistory(token);
                if (cancelled) {
                    return;
                }

                setHistory(items);
            } catch (error) {
                if (cancelled) {
                    return;
                }

                window.localStorage.removeItem(TOKEN_KEY);
                setToken("");
                setUser(null);
                setHistory([]);
                setActiveHistoryId(null);
                setAuthError("Your saved session expired. Sign in again to continue.");
            } finally {
                if (!cancelled) {
                    setLoadingHistory(false);
                    setAuthReady(true);
                }
            }
        }

        restoreSession();

        return () => {
            cancelled = true;
        };
    }, [token]);

    useEffect(() => {
        if (!selectedClaim || !data?.claims?.length) return;
        const fresh = data.claims.find(
            (c) => c.start_idx === selectedClaim.start_idx && c.end_idx === selectedClaim.end_idx
        );
        if (fresh && fresh !== selectedClaim) {
            setSelectedClaim(fresh);
        }
    }, [data?.claims, selectedClaim]);

    const persistToken = (nextToken) => {
        if (nextToken) {
            window.localStorage.setItem(TOKEN_KEY, nextToken);
        } else {
            window.localStorage.removeItem(TOKEN_KEY);
        }

        setToken(nextToken);
    };

    const resetWorkspace = () => {
        if (streamAbortRef.current) {
            streamAbortRef.current.abort();
            streamAbortRef.current = null;
        }
        setDocument("");
        setData(null);
        setSelectedClaim(null);
        setStatus("");
        setWorkspaceError("");
        setLoading(false);
        setActiveHistoryId(null);
        setExtractedFile(null);
        if (fileInputRef.current) {
            fileInputRef.current.value = "";
        }
    };

    const refreshHistory = async (sessionToken = token, preferredHistoryId = null) => {
        if (!sessionToken) {
            return [];
        }

        setLoadingHistory(true);

        try {
            const items = await listHistory(sessionToken);
            setHistory(items);
            setActiveHistoryId((current) => {
                if (preferredHistoryId) {
                    return preferredHistoryId;
                }

                if (current && items.some((item) => item.id === current)) {
                    return current;
                }

                return current;
            });
            return items;
        } catch (error) {
            setWorkspaceError(error.message);
            return [];
        } finally {
            setLoadingHistory(false);
        }
    };

    const openHistoryItem = async (historyId, { quiet = false } = {}) => {
        if (!token) {
            return;
        }

        if (!quiet) {
            setStatus("Loading saved audit...");
        }
        setWorkspaceError("");

        try {
            const detail = await getHistoryDetail(historyId, token);
            setDocument(detail.audit.document);
            setData(detail.audit);
            setSelectedClaim(null);
            setActiveHistoryId(historyId);
        } catch (error) {
            setWorkspaceError(error.message);
        } finally {
            if (!quiet) {
                setStatus("");
            }
        }
    };

    const handleAuthFieldChange = (event) => {
        const { name, value } = event.target;
        setAuthForm((previous) => ({
            ...previous,
            [name]: value,
        }));
    };

    const handleAuthModeChange = (mode) => {
        setAuthMode(mode);
        setAuthError("");
    };

    const handleAuthSubmit = async (event) => {
        event.preventDefault();
        setAuthLoading(true);
        setAuthError("");
        setWorkspaceError("");

        try {
            const action = authMode === "login" ? login : register;
            const response = await action(authForm);
            setUser(response.user);
            persistToken(response.token);
            setAuthForm({ username: "", password: "" });
        } catch (error) {
            setAuthError(error.message);
        } finally {
            setAuthLoading(false);
        }
    };

    const handleLogout = async () => {
        try {
            if (token) {
                await logout(token);
            }
        } catch {
            // ignore
        }

        persistToken("");
        setUser(null);
        setHistory([]);
        setAuthError("");
        resetWorkspace();
    };

    const handleStreamUpdate = (update) => {
        if (update.type === "start") {
            setData({
                ...EMPTY_AUDIT,
                total: update.total,
            });
            setStatus(`Verifying ${update.total} claims...`);
            return;
        }

        if (update.type === "claims_extracted") {
            setData((previous) => ({
                ...(previous ?? EMPTY_AUDIT),
                claims: update.claims || [],
                total: update.total ?? previous?.total ?? 0,
            }));
            return;
        }

        if (update.type === "claim") {
            setData((previous) => {
                const baseline = previous ?? EMPTY_AUDIT;
                const claims = [...(baseline.claims || [])];
                const idx = claims.findIndex((item) => item.start_idx === update.claim.start_idx && item.end_idx === update.claim.end_idx);
                if (idx >= 0) {
                    claims[idx] = update.claim;
                } else {
                    claims.push(update.claim);
                }

                return {
                    ...baseline,
                    claims,
                    verified: claims.filter((claim) => claim.status === "Verified").length,
                    plausible: claims.filter((claim) => claim.status === "Plausible").length,
                    hallucinations: claims.filter((claim) => claim.status === "Hallucination").length,
                };
            });
            return;
        }

        if (update.type === "progress") {
            setStatus(`Verified ${update.completed || 0}/${update.total || 0} claims...`);
            return;
        }

        if (update.type === "heartbeat") {
            const inflight = update.in_flight ?? 0;
            setStatus(`Running... ${update.completed || 0}/${update.total || 0} completed, ${inflight} in-flight`);
            return;
        }

        if (update.type === "status" || update.type === "stage") {
            setStatus(update.message || "Processing...");
            return;
        }

        if (update.type === "done") {
            setLoading(false);
            setStatus("");
            return;
        }

        if (update.type === "stream_end") {
            setLoading(false);
            setStatus("Completed");
            return;
        }

        if (update.type === "cancelled") {
            setLoading(false);
            setStatus("Cancelled");
            return;
        }

        if (update.type === "error") {
            setLoading(false);
            setStatus("");
            setWorkspaceError(update.message);
        }
    };

    const handleAudit = async () => {
        if (!document.trim() || !token) {
            return;
        }

        if (streamAbortRef.current) {
            streamAbortRef.current.abort();
        }
        const controller = new AbortController();
        streamAbortRef.current = controller;

        setLoading(true);
        setWorkspaceError("");
        setData({ ...EMPTY_AUDIT });
        setStatus("Analyzing document structure...");
        setSelectedClaim(null);
        setActiveHistoryId(null);

        const donePayload = await runAuditStream(document, handleStreamUpdate, token, controller.signal);

        if (donePayload?.history_id) {
            await refreshHistory(token, donePayload.history_id);
            await openHistoryItem(donePayload.history_id, { quiet: true });
        } else {
            await refreshHistory(token);
        }

        if (streamAbortRef.current === controller) {
            streamAbortRef.current = null;
        }
    };

    const processFile = async (file) => {
        if (!file || !token) return;

        setLoading(true);
        setWorkspaceError("");
        setData(null);
        setStatus(`Extracting readable text from ${file.name}...`);
        setSelectedClaim(null);
        setActiveHistoryId(null);

        const formData = new FormData();
        formData.append("file", file);

        try {
            const result = await extractTextFromDocument(formData, token);
            setDocument(result.text);
            setExtractedFile({
                filename: result.filename,
                characters: result.characters,
            });
            setStatus(`Extracted ${result.characters.toLocaleString()} readable characters from ${result.filename}.`);
        } catch (error) {
            setWorkspaceError(error.message);
            setStatus("");
        } finally {
            setLoading(false);
        }
    };

    const handleFileInputChange = async (event) => {
        const file = event.target.files?.[0];
        if (!file) return;
        await processFile(file);
        event.target.value = "";
    };

    const handleDrop = async (event) => {
        event.preventDefault();
        setIsDragOver(false);
        const file = event.dataTransfer.files?.[0];
        if (file) {
            await processFile(file);
        }
    };

    const handleLoadSample = async () => {
        setLoading(true);
        setWorkspaceError("");
        setStatus("Loading sample data...");

        try {
            const result = await loadSample();
            setData(result);
            setDocument(result.document);
            setSelectedClaim(null);
            setActiveHistoryId(null);
        } catch (error) {
            setWorkspaceError(error.message);
        } finally {
            setLoading(false);
            setStatus("");
        }
    };

    if (!authReady) {
        return (
            <div className="flex min-h-screen items-center justify-center bg-[#0a0c10] px-4 text-sm font-semibold uppercase tracking-[0.3em] text-gray-400">
                Loading workspace...
            </div>
        );
    }

    if (!user) {
        return (
            <AuthScreen
                mode={authMode}
                form={authForm}
                loading={authLoading}
                error={authError}
                onFieldChange={handleAuthFieldChange}
                onModeChange={handleAuthModeChange}
                onSubmit={handleAuthSubmit}
            />
        );
    }

    return (
        <div className="min-h-screen bg-[#0a0c10] text-gray-100 lg:grid lg:grid-cols-[320px_minmax(0,1fr)]">
            <HistorySidebar
                user={user}
                history={history}
                activeHistoryId={activeHistoryId}
                loadingHistory={loadingHistory}
                onNewAudit={resetWorkspace}
                onSelectHistory={openHistoryItem}
                onLogout={handleLogout}
            />

            <div className="min-h-screen px-4 py-6 sm:px-6 lg:px-8">
                <header className="mx-auto mb-8 flex max-w-7xl flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
                    <div className="space-y-2">
                        <div className="text-xs font-semibold uppercase tracking-[0.28em] text-blue-200/70">
                            Authenticated Workspace
                        </div>
                        <div>
                            <h1 className="text-3xl font-black tracking-tight text-white sm:text-4xl">
                                SAMSA Auditor
                            </h1>
                            <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-400 sm:text-base">
                                Run new audits, reopen previous results, and keep everything tied to your local account.
                            </p>
                        </div>
                    </div>

                    <div className="flex items-center gap-4">
                        <button
                            type="button"
                            onClick={handleLoadSample}
                            disabled={loading}
                            className="rounded-2xl border border-white/10 px-4 py-3 text-sm font-semibold text-gray-300 transition hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
                        >
                            Load Sample
                        </button>
                    </div>
                </header>

                {workspaceError ? (
                    <div className="mx-auto mb-6 max-w-7xl rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">
                        {workspaceError}
                    </div>
                ) : null}

                {status ? (
                    <div className="mx-auto mb-6 max-w-7xl rounded-2xl border border-blue-500/20 bg-blue-500/10 px-4 py-3 text-sm text-blue-100">
                        {status}
                    </div>
                ) : null}

                <main className="mx-auto grid max-w-7xl grid-cols-1 gap-8 lg:grid-cols-12">
                    <div className="space-y-6 lg:col-span-8">
                        {!data || data.claims.length === 0 ? (
                            <div
                                className={`rounded-[2rem] border bg-[#101318] p-6 shadow-[0_24px_60px_rgba(0,0,0,0.35)] transition-all ${
                                    isDragOver ? "border-blue-400/60 bg-[#121923]" : "border-white/10"
                                }`}
                                onDragOver={(event) => {
                                    event.preventDefault();
                                    setIsDragOver(true);
                                }}
                                onDragLeave={(event) => {
                                    event.preventDefault();
                                    setIsDragOver(false);
                                }}
                                onDrop={handleDrop}
                            >
                                <textarea
                                    className="h-72 w-full resize-none rounded-[1.5rem] border border-white/10 bg-[#0b0f14] px-5 py-5 text-base leading-7 text-gray-100 outline-none transition focus:border-blue-400/60 focus:ring-2 focus:ring-blue-500/20 sm:text-lg"
                                    placeholder="Paste your document here or upload a PDF, DOCX, PPTX, or text file..."
                                    value={document}
                                    onChange={(event) => {
                                        setDocument(event.target.value);
                                        setExtractedFile(null);
                                    }}
                                />
                                {extractedFile ? (
                                    <div className="mt-4 rounded-2xl border border-green-500/20 bg-green-500/10 px-4 py-3 text-sm text-green-100">
                                        Loaded {extractedFile.filename} with {extractedFile.characters.toLocaleString()} readable characters.
                                    </div>
                                ) : null}
                                <div className="mt-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                                    <input
                                        ref={fileInputRef}
                                        type="file"
                                        accept=".pdf,.docx,.pptx,.txt,.md,.csv,.json,.html,.htm,.xml,.log"
                                        className="hidden"
                                        onChange={handleFileInputChange}
                                    />
                                    <button
                                        type="button"
                                        onClick={() => fileInputRef.current?.click()}
                                        disabled={loading}
                                        className="flex w-full items-center justify-center gap-3 rounded-[1.5rem] border border-white/10 px-4 py-4 text-sm font-bold uppercase tracking-[0.22em] text-gray-200 transition hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
                                    >
                                        Upload document
                                    </button>
                                    <button
                                        type="button"
                                        onClick={handleAudit}
                                        disabled={loading || !document.trim()}
                                        className="flex w-full items-center justify-center gap-3 rounded-[1.5rem] bg-blue-600 px-4 py-4 text-sm font-bold uppercase tracking-[0.22em] text-white transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-gray-700"
                                    >
                                        {loading ? "Working..." : "Start audit"}
                                    </button>
                                </div>
                            </div>
                        ) : (
                            <>
                                <Summary data={data} />
                                <DocumentViewer
                                    text={document}
                                    claims={data.claims}
                                    onSelectClaim={setSelectedClaim}
                                    selectedClaim={selectedClaim}
                                />
                                <button
                                    type="button"
                                    onClick={resetWorkspace}
                                    className="text-sm font-semibold text-gray-400 transition hover:text-white"
                                >
                                    Back to editor
                                </button>
                            </>
                        )}
                    </div>

                    <div className="lg:col-span-4 lg:sticky lg:top-6 lg:h-[calc(100vh-3rem)]">
                        <DetailPanel claim={selectedClaim} />
                    </div>
                </main>
            </div>
        </div>
    );
}

export default App;
