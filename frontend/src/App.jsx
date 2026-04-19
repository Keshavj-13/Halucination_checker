import { useState, useEffect, useRef } from "react";
import { runAuditStream, loadSample, extractTextFromDocument } from "./api";
import Summary from "./components/Summary";
import DocumentViewer from "./components/DocumentViewer";
import DetailPanel from "./components/DetailPanel";

function App() {
    const fileInputRef = useRef(null);
    const [document, setDocument] = useState("");
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [status, setStatus] = useState("");
    const [selectedClaim, setSelectedClaim] = useState(null);
    const [progress, setProgress] = useState({ completed: 0, total: 0 });
    const [resources, setResources] = useState(null);
    const [scrapeStats, setScrapeStats] = useState({ urls_discovered: 0, started: 0, done: 0, cache_hits: 0, failed: 0 });
    const [isDragOver, setIsDragOver] = useState(false);
    const [extractedFile, setExtractedFile] = useState(null);
    const streamAbortRef = useRef(null);

    useEffect(() => {
        if (!selectedClaim || !data?.claims?.length) return;
        const fresh = data.claims.find(
            (c) => c.start_idx === selectedClaim.start_idx && c.end_idx === selectedClaim.end_idx
        );
        if (fresh && fresh !== selectedClaim) {
            setSelectedClaim(fresh);
        }
    }, [data?.claims, selectedClaim]);

    const mergeClaim = (existingClaims, incomingClaim) => {
        const idx = existingClaims.findIndex(
            (c) => c.start_idx === incomingClaim.start_idx && c.end_idx === incomingClaim.end_idx
        );
        if (idx === -1) return [...existingClaims, incomingClaim];
        const next = [...existingClaims];
        next[idx] = incomingClaim;
        return next;
    };

    const handleAudit = async () => {
        if (!document.trim()) return;

        if (streamAbortRef.current) {
            streamAbortRef.current.abort();
        }
        const controller = new AbortController();
        streamAbortRef.current = controller;

        setLoading(true);
        setData({ claims: [], total: 0, verified: 0, plausible: 0, hallucinations: 0 });
        setStatus("Analyzing document structure...");
        setProgress({ completed: 0, total: 0 });
        setResources(null);
        setScrapeStats({ urls_discovered: 0, started: 0, done: 0, cache_hits: 0, failed: 0 });
        setSelectedClaim(null);

        await runAuditStream(document, (update) => {
            if (update.type === "start") {
                setData(prev => ({ ...prev, total: update.total }));
                setStatus(`Verifying ${update.total} claims...`);
                setProgress({ completed: 0, total: update.total });
            } else if (update.type === "resources") {
                setResources(update.resources || null);
            } else if (update.type === "stage") {
                setStatus(update.message || "Processing...");
            } else if (update.type === "claims_extracted") {
                setData(prev => ({ ...prev, claims: update.claims || [] }));
            } else if (update.type === "claim") {
                setData(prev => {
                    const newClaims = mergeClaim(prev.claims || [], update.claim);
                    const verified = newClaims.filter(c => c.status === "Verified").length;
                    const plausible = newClaims.filter(c => c.status === "Plausible").length;
                    const hallucinations = newClaims.filter(c => c.status === "Hallucination").length;
                    return {
                        ...prev,
                        claims: newClaims,
                        verified,
                        plausible,
                        hallucinations
                    };
                });
                setSelectedClaim((prev) => {
                    if (!prev) return update.claim;
                    if (prev.start_idx === update.claim.start_idx && prev.end_idx === update.claim.end_idx) {
                        return update.claim;
                    }
                    return prev;
                });
                setProgress({ completed: update.completed || 0, total: update.total || 0 });
            } else if (update.type === "progress") {
                setData(prev => ({
                    ...prev,
                    verified: update.verified ?? prev.verified,
                    plausible: update.plausible ?? prev.plausible,
                    hallucinations: update.hallucinations ?? prev.hallucinations,
                }));
                if (update.scrape) {
                    setScrapeStats(update.scrape);
                }
                setProgress({ completed: update.completed || 0, total: update.total || 0 });
                setStatus(`Verified ${update.completed || 0}/${update.total || 0} claims...`);
            } else if (update.type === "heartbeat") {
                setProgress({ completed: update.completed || 0, total: update.total || 0 });
                const inflight = update.in_flight ?? 0;
                const s = update.scrape || scrapeStats;
                if (update.scrape) {
                    setScrapeStats(update.scrape);
                }
                setStatus(
                    `Running... ${update.completed || 0}/${update.total || 0} completed, ${inflight} in-flight · scraping ${s.done || 0}/${s.urls_discovered || 0} (cache ${s.cache_hits || 0}, fail ${s.failed || 0})`
                );
            } else if (update.type === "done") {
                setLoading(false);
                setProgress({ completed: update.total || progress.total, total: update.total || progress.total });
                setStatus("Completed");
            } else if (update.type === "stream_end") {
                setLoading(false);
                setStatus("Completed");
            } else if (update.type === "cancelled") {
                setLoading(false);
                setStatus("Cancelled");
            } else if (update.type === "error") {
                setLoading(false);
                setStatus("Error: " + update.message);
            }
        }, controller.signal);

        if (streamAbortRef.current === controller) {
            streamAbortRef.current = null;
        }
    };

    const handleBackToEditor = () => {
        if (streamAbortRef.current) {
            streamAbortRef.current.abort();
            streamAbortRef.current = null;
        }
        setLoading(false);
        setStatus("");
        setData(null);
        setSelectedClaim(null);
    };

    const processFile = async (file) => {
        if (!file) return;

        setLoading(true);
        setStatus(`Extracting readable text from ${file.name}...`);
        setSelectedClaim(null);
        setExtractedFile(null);

        const formData = new FormData();
        formData.append("file", file);
        const result = await extractTextFromDocument(formData);

        if (!result || !result.text) {
            setStatus("Error: failed to extract text from file");
            setLoading(false);
            return;
        }

        setDocument(result.text);
        setExtractedFile({ filename: result.filename, characters: result.characters });
        setStatus(`Extracted ${result.characters?.toLocaleString?.() ?? result.characters} chars from ${result.filename}`);
        setLoading(false);
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
        setStatus("Loading sample data...");
        const result = await loadSample();
        setData(result);
        setDocument(result.document);
        setLoading(false);
        setStatus("");
        setProgress({ completed: result.total || 0, total: result.total || 0 });
        setSelectedClaim(null);
    };

    return (
        <div className="min-h-screen bg-gray-950 text-gray-100 p-4 sm:p-8">
            <header className="max-w-7xl mx-auto mb-8 flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-black tracking-tighter text-white">
                        SAMSA <span className="text-blue-500">AUDITOR</span>
                    </h1>
                    <p className="text-gray-500 text-sm font-medium">Multilayer Ensemble Hallucination Detection</p>
                </div>
                <div className="flex gap-4">
                    <button
                        onClick={handleLoadSample}
                        disabled={loading}
                        className="text-gray-400 hover:text-white text-sm font-bold transition-colors"
                    >
                        Load Sample
                    </button>
                    <div className="h-8 w-px bg-gray-800" />
                    <div className="flex items-center gap-2">
                        <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                        <span className="text-xs font-bold text-gray-400 uppercase tracking-widest">System Ready</span>
                    </div>
                </div>
            </header>

            <main className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-8">
                {/* Input & Viewer Column */}
                <div className="lg:col-span-8 space-y-6">
                    {!data ? (
                        <div className="bg-gray-900 rounded-2xl p-6 shadow-xl border border-gray-800">
                            <div
                                onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
                                onDragLeave={(e) => { e.preventDefault(); setIsDragOver(false); }}
                                onDrop={handleDrop}
                                className={`mb-4 rounded-xl border border-dashed p-4 text-sm transition-colors ${isDragOver ? "border-blue-400 bg-blue-500/10 text-blue-200" : "border-gray-700 bg-gray-950/60 text-gray-400"}`}
                            >
                                <div className="flex items-center justify-between gap-3">
                                    <span>Drop a file here (PDF, DOCX, PPTX, TXT, MD, CSV, JSON, HTML, XML, LOG)</span>
                                    <button
                                        type="button"
                                        onClick={() => fileInputRef.current?.click()}
                                        className="px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-200 font-semibold"
                                    >
                                        Upload File
                                    </button>
                                </div>
                                {extractedFile && (
                                    <div className="mt-2 text-xs text-cyan-300 font-mono">
                                        Loaded: {extractedFile.filename} ({extractedFile.characters} chars)
                                    </div>
                                )}
                                <input
                                    ref={fileInputRef}
                                    type="file"
                                    className="hidden"
                                    onChange={handleFileInputChange}
                                    accept=".pdf,.docx,.pptx,.txt,.md,.csv,.json,.html,.htm,.xml,.log"
                                />
                            </div>
                            <textarea
                                className="w-full h-64 bg-gray-950 text-gray-100 p-6 rounded-xl border border-gray-800 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all resize-none text-lg font-serif leading-relaxed"
                                placeholder="Paste your document here to begin the audit..."
                                value={document}
                                onChange={(e) => setDocument(e.target.value)}
                            />
                            <button
                                onClick={handleAudit}
                                disabled={loading || !document.trim()}
                                className="w-full mt-4 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-800 text-white font-black py-4 rounded-xl transition-all shadow-lg active:scale-[0.98] flex items-center justify-center gap-3 text-lg"
                            >
                                {loading ? (
                                    <>
                                        <svg className="animate-spin h-6 w-6 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                        </svg>
                                        {status || "Running Audit..."}
                                    </>
                                ) : "START AUDIT"}
                            </button>
                        </div>
                    ) : (
                        <>
                            <div className="bg-gray-900 rounded-2xl p-4 border border-gray-800 text-sm text-gray-300 flex items-center justify-between">
                                <span>{status || "Ready"}</span>
                                <div className="flex items-center gap-4">
                                    {resources && (
                                        <span className="font-mono text-[11px] text-cyan-300">
                                            C:{resources.max_claims_in_flight} V:{resources.voter_cpu_workers} S:{resources.scrape_concurrency} G:{resources.ollama_num_gpu}
                                        </span>
                                    )}
                                    <span className="font-mono text-[11px] text-amber-300">
                                        scrape {scrapeStats.done}/{scrapeStats.urls_discovered} c{scrapeStats.cache_hits} f{scrapeStats.failed}
                                    </span>
                                    <span className="font-mono text-gray-400">{progress.completed}/{progress.total || data.total || 0}</span>
                                </div>
                            </div>
                            <Summary data={data} />
                            <DocumentViewer
                                text={document}
                                claims={data.claims}
                                onSelectClaim={setSelectedClaim}
                                selectedClaim={selectedClaim}
                            />
                            <button
                                onClick={handleBackToEditor}
                                className="text-gray-500 hover:text-gray-300 text-sm font-bold flex items-center gap-2 transition-colors"
                            >
                                ← Back to Editor
                            </button>
                        </>
                    )}
                </div>

                {/* Side Dashboard Column */}
                <div className="lg:col-span-4 sticky top-8 h-[calc(100vh-8rem)]">
                    <DetailPanel claim={selectedClaim} loading={loading} status={status} progress={progress} resources={resources} scrapeStats={scrapeStats} />
                </div>
            </main>
        </div>
    );
}

export default App;
