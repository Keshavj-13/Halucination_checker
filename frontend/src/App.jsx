import { useState } from "react";
import { runAudit, loadSample } from "./api";
import Summary from "./components/Summary";
import ClaimCard from "./components/ClaimCard";

function App() {
    const [document, setDocument] = useState("");
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [status, setStatus] = useState("");

    const handleAudit = async () => {
        if (!document.trim()) return;
        setLoading(true);
        setStatus("Extracting atomic claims...");

        try {
            // Note: In a real "Strong" pipeline, we might use WebSockets to stream 
            // progress for each claim (Query -> Search -> Verify). 
            // For this demo, we'll stick to a single request but with a clear status.
            const result = await runAudit(document);
            setData(result);
        } catch (err) {
            console.error(err);
            setStatus("Error occurred during audit.");
        } finally {
            setLoading(false);
            setStatus("");
        }
    };

    const handleLoadSample = async () => {
        setLoading(true);
        setStatus("Loading sample data...");
        const result = await loadSample();
        setData(result);
        setDocument("The Earth orbits the Sun at an average distance of 93 million miles. Python is the best programming language and always outperforms every other language. Machine learning models can improve over time with more data. The human brain contains approximately 86 billion neurons. Renewable energy is always cheaper than fossil fuels in every region.");
        setLoading(false);
        setStatus("");
    };

    return (
        <div className="min-h-screen p-4 sm:p-8 max-w-4xl mx-auto">
            <header className="mb-8 text-center">
                <h1 className="text-4xl font-extrabold tracking-tight text-white mb-2">
                    Hallucination <span className="text-blue-500">Audit</span>
                </h1>
                <p className="text-gray-400">Verify claims using Search-Augmented AI (RAG).</p>
            </header>

            <section className="bg-gray-800 rounded-2xl p-6 shadow-xl border border-gray-700 mb-8">
                <textarea
                    className="w-full h-40 bg-gray-900 text-gray-100 p-4 rounded-xl border border-gray-700 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all resize-none"
                    placeholder="Paste your document here..."
                    value={document}
                    onChange={(e) => setDocument(e.target.value)}
                />
                <div className="flex flex-wrap gap-4 mt-4">
                    <button
                        onClick={handleAudit}
                        disabled={loading || !document.trim()}
                        className="flex-1 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 text-white font-bold py-3 px-6 rounded-xl transition-all shadow-lg active:scale-95 flex items-center justify-center gap-2"
                    >
                        {loading ? (
                            <>
                                <svg className="animate-spin h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                {status || "Running Audit..."}
                            </>
                        ) : "Run Audit"}
                    </button>
                    <button
                        onClick={handleLoadSample}
                        disabled={loading}
                        className="bg-gray-700 hover:bg-gray-600 text-gray-200 font-semibold py-3 px-6 rounded-xl transition-all active:scale-95"
                    >
                        Load Sample
                    </button>
                </div>
            </section>

            {data && (
                <main className="animate-in fade-in slide-in-from-bottom-4 duration-500">
                    <Summary data={data} />

                    <div className="space-y-4">
                        <div className="flex items-center justify-between mb-4 px-1">
                            <h2 className="text-xl font-bold text-gray-200">Extracted Claims</h2>
                            <div className="flex gap-2">
                                <span className="text-[10px] uppercase tracking-wider font-bold text-blue-400 bg-blue-900/30 px-2 py-1 rounded border border-blue-800/50">
                                    Search Augmented
                                </span>
                                <span className="text-[10px] uppercase tracking-wider font-bold text-purple-400 bg-purple-900/30 px-2 py-1 rounded border border-purple-800/50">
                                    Atomic Extraction
                                </span>
                            </div>
                        </div>
                        {data.claims.map((claim, idx) => (
                            <ClaimCard key={idx} claim={claim} index={idx} />
                        ))}
                    </div>
                </main>
            )}
        </div>
    );
}

export default App;
