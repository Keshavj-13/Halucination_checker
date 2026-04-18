import React from 'react';

const DetailPanel = ({ claim }) => {
    if (!claim) {
        return (
            <div className="bg-gray-800 rounded-2xl p-6 border border-gray-700 h-full flex items-center justify-center text-gray-500 italic">
                Select a highlighted line to see audit details.
            </div>
        );
    }

    const getStatusColor = (status) => {
        if (status === "Verified") return "text-green-400";
        if (status === "Hallucination") return "text-red-400";
        return "text-yellow-400";
    };

    return (
        <div className="bg-gray-800 rounded-2xl p-6 border border-gray-700 h-full overflow-y-auto space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
            <header>
                <div className="flex items-center justify-between mb-2">
                    <span className={`text-sm font-bold uppercase tracking-widest ${getStatusColor(claim.status)}`}>
                        {claim.status}
                    </span>
                    <span className="text-gray-400 text-sm font-mono">
                        Confidence: {Math.round(claim.confidence * 100)}%
                    </span>
                </div>
                <h3 className="text-xl font-bold text-white leading-tight">
                    "{claim.text}"
                </h3>
            </header>

            <section>
                <h4 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-3">Voter Scorecard</h4>
                <div className="grid grid-cols-2 gap-3">
                    {Object.entries(claim.voter_scores || {}).map(([voter, score]) => (
                        <div key={voter} className="bg-gray-900/50 p-3 rounded-xl border border-gray-700/50">
                            <div className="text-[10px] text-gray-500 uppercase font-bold mb-1">{voter}</div>
                            <div className="flex items-center gap-2">
                                <div className="h-1.5 flex-1 bg-gray-700 rounded-full overflow-hidden">
                                    <div
                                        className={`h-full ${score > 0.7 ? 'bg-green-500' : score > 0.3 ? 'bg-yellow-500' : 'bg-red-500'}`}
                                        style={{ width: `${score * 100}%` }}
                                    />
                                </div>
                                <span className="text-xs font-mono text-gray-300">{Math.round(score * 100)}%</span>
                            </div>
                        </div>
                    ))}
                </div>
            </section>

            <section>
                <h4 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-3">Evidence & Sources</h4>
                <div className="space-y-4">
                    {claim.evidence.map((ev, i) => (
                        <div key={i} className="bg-gray-900 p-4 rounded-xl border-l-4 border-blue-500 shadow-lg">
                            <div className="flex items-center justify-between mb-2">
                                <a
                                    href={ev.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-blue-400 hover:text-blue-300 font-bold text-sm truncate max-w-[200px]"
                                >
                                    {ev.title}
                                </a>
                                <span className="bg-blue-900/30 text-blue-400 text-[10px] px-2 py-0.5 rounded-full border border-blue-800/50">
                                    Reliability: {Math.round(ev.reliability_score * 100)}%
                                </span>
                            </div>
                            <p className="text-gray-400 text-sm leading-relaxed italic">
                                "{ev.snippet.length > 200 ? ev.snippet.substring(0, 200) + '...' : ev.snippet}"
                            </p>
                        </div>
                    ))}
                </div>
            </section>
        </div>
    );
};

export default DetailPanel;
