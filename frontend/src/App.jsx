import { useState, useEffect } from "react";
import { runAuditStream, loadSample } from "./api";
import Summary from "./components/Summary";
import DocumentViewer from "./components/DocumentViewer";
import DetailPanel from "./components/DetailPanel";

function App() {
    const [document, setDocument] = useState("");
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [status, setStatus] = useState("");
    const [selectedClaim, setSelectedClaim] = useState(null);
    const [isDragOver, setIsDragOver] = useState(false);

    const handleAudit = async () => {
        if (!document.trim()) return;

        setLoading(true);
        setData({ claims: [], total: 0, verified: 0, plausible: 0, hallucinations: 0 });
        setStatus("Analyzing document structure...");
        setSelectedClaim(null);

        await runAuditStream(document, (update) => {
            if (update.type === "start") {
                setData(prev => ({ ...prev, total: update.total }));
                setStatus(`Verifying ${update.total} claims...`);
            } else if (update.type === "claim") {
                setData(prev => {
                    const newClaims = [...prev.claims, update.claim];
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
            } else if (update.type === "done") {
                setLoading(false);
                setStatus("");
            } else if (update.type === "error") {
                setLoading(false);
                setStatus("Error: " + update.message);
            }
        });
    };

    const handleLoadSample = async () => {
        setLoading(true);
        setStatus("Loading sample data...");
        const result = await loadSample();
        setData(result);
        setDocument(result.document);
        setLoading(false);
        setStatus("");
        setSelectedClaim(null);
    };

    const handleDragOver = (e) => {
        e.preventDefault();
        setIsDragOver(true);
    };

    const handleDragLeave = (e) => {
        e.preventDefault();
        setIsDragOver(false);
    };

    const handleDrop = async (e) => {
        e.preventDefault();
        setIsDragOver(false);
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            const file = files[0];
            // Accept any file that might contain text
            await processFile(file);
        }
    };

    const processFile = async (file) => {
        setLoading(true);
        setData({ claims: [], total: 0, verified: 0, plausible: 0, hallucinations: 0 });
        setStatus("Processing file...");
        setSelectedClaim(null);

        const formData = new FormData();
        formData.append('file', file);

        try {
            await runAuditStream(formData, (update) => {
                if (update.type === "start") {
                    setData(prev => ({ ...prev, total: update.total }));
                    setStatus(`Verifying ${update.total} claims...`);
                } else if (update.type === "claim") {
                    setData(prev => {
                        const newClaims = [...prev.claims, update.claim];
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
                } else if (update.type === "done") {
                    setLoading(false);
                    setStatus("");
                } else if (update.type === "error") {
                    setLoading(false);
                    setStatus("Error: " + update.message);
                }
            });
        } catch (error) {
            setLoading(false);
            setStatus("Error processing file: " + error.message);
        }
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
                    {!data || data.claims.length === 0 ? (
                        <div 
                            className={`bg-gray-900 rounded-2xl p-6 shadow-xl border transition-all ${isDragOver ? 'border-blue-500 bg-gray-800' : 'border-gray-800'}`}
                            onDragOver={handleDragOver}
                            onDragLeave={handleDragLeave}
                            onDrop={handleDrop}
                        >
                            <textarea
                                className="w-full h-64 bg-gray-950 text-gray-100 p-6 rounded-xl border border-gray-800 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all resize-none text-lg font-serif leading-relaxed"
                                placeholder="Paste your document here or drop any text file (PDF, DOCX, TXT, etc.) to begin the audit..."
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
                            <Summary data={data} />
                            <DocumentViewer
                                text={document}
                                claims={data.claims}
                                onSelectClaim={setSelectedClaim}
                                selectedClaim={selectedClaim}
                            />
                            <button
                                onClick={() => setData(null)}
                                className="text-gray-500 hover:text-gray-300 text-sm font-bold flex items-center gap-2 transition-colors"
                            >
                                ← Back to Editor
                            </button>
                        </>
                    )}
                </div>

                {/* Side Dashboard Column */}
                <div className="lg:col-span-4 sticky top-8 h-[calc(100vh-8rem)]">
                    <DetailPanel claim={selectedClaim} />
                </div>
            </main>
        </div>
    );
}

export default App;
