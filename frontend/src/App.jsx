import { useState } from "react";
import { runAudit, loadSample } from "./api";
import Summary from "./components/Summary";
import ClaimCard from "./components/ClaimCard";

function App() {
    const [document, setDocument] = useState("");
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);

    const handleAudit = async () => {
        if (!document.trim()) return;
        setLoading(true);
        const result = await runAudit(document);
        setData(result);
        setLoading(false);
    };

    const handleLoadSample = async () => {
        setLoading(true);
        const result = await loadSample();
        setData(result);
        setDocument("The Earth orbits the Sun at an average distance of 93 million miles. Python is the best programming language and always outperforms every other language. Machine learning models can improve over time with more data. The human brain contains approximately 86 billion neurons. Renewable energy is always cheaper than fossil fuels in every region.");
        setLoading(false);
    };

    return (
        <div className="min-h-screen p-4 sm:p-8 max-w-4xl mx-auto">
            <header className="mb-8 text-center">
                <h1 className="text-4xl font-extrabold tracking-tight text-white mb-2">
                    Hallucination <span className="text-blue-500">Audit</span>
                </h1>
                <p className="text-gray-400">Verify claims and detect hallucinations in your documents.</p>
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
                        className="flex-1 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 text-white font-bold py-3 px-6 rounded-xl transition-all shadow-lg active:scale-95"
                    >
                        {loading ? "Running Audit..." : "Run Audit"}
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
                        <h2 className="text-xl font-bold text-gray-200 mb-4 px-1">Extracted Claims</h2>
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
