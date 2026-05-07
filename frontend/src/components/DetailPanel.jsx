import React from 'react';

const DetailPanel = ({ claim, loading = false, status = '', progress = null, resources = null, scrapeStats = null }) => {
    if (!claim) {
        return (
            <div className="bg-gray-800 rounded-2xl p-6 border border-gray-700 h-full flex flex-col items-center justify-center text-gray-500 italic gap-4">
                {loading ? (
                    <>
                        <div className="w-full space-y-3 max-w-sm">
                            <div className="h-4 w-2/3 bg-gray-700/70 rounded animate-pulse" />
                            <div className="h-3 w-full bg-gray-700/50 rounded animate-pulse" />
                            <div className="h-3 w-5/6 bg-gray-700/50 rounded animate-pulse" />
                            <div className="h-3 w-3/4 bg-gray-700/50 rounded animate-pulse" />
                        </div>
                        <p className="text-sm not-italic text-gray-400 text-center">{status || 'Running verification pipeline...'}</p>
                        {progress && progress.total > 0 && (
                            <p className="text-xs not-italic text-gray-500">
                                Completed {progress.completed}/{progress.total} claims
                            </p>
                        )}
                        {resources && (
                            <p className="text-xs not-italic text-cyan-300 font-mono text-center">
                                claims={resources.max_claims_in_flight} voters={resources.voter_cpu_workers} scrape={resources.scrape_concurrency} embed={resources.embedding_batch_size}/{resources.embedding_max_in_flight} gpu={resources.ollama_num_gpu}
                            </p>
                        )}
                        {scrapeStats && (
                            <p className="text-xs not-italic text-amber-300 font-mono text-center">
                                webscrape done={scrapeStats.done} discovered={scrapeStats.urls_discovered} cache={scrapeStats.cache_hits} failed={scrapeStats.failed}
                            </p>
                        )}
                    </>
                ) : (
                    <>Select a highlighted line to see audit details.</>
                )}
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
                        Confidence: {Math.round((claim.confidence || 0) * 100)}%
                    </span>
                </div>
                <h3 className="text-xl font-bold text-white leading-tight">
                    "{claim.text}"
                </h3>
                <p className="text-gray-500 text-xs mt-2 font-mono">
                    Final Score: {((claim.final_score ?? claim.confidence ?? 0) * 100).toFixed(1)}%
                </p>
            </header>

            {claim.source_reliability_explanation && (
                <section>
                    <h4 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-2">Source Reliability</h4>
                    <p className="text-sm text-gray-400">{claim.source_reliability_explanation}</p>
                </section>
            )}

            <section>
                <h4 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-3">Voter Analysis</h4>
                <div className="space-y-3">
                    {claim.voter_results && Object.keys(claim.voter_results).length > 0 ? (
                        Object.entries(claim.voter_results).map(([voterName, voterResult]) => (
                            <div key={voterName} className="bg-gray-900/50 p-3 rounded-xl border border-gray-700/50">
                                <div className="flex items-center justify-between mb-2">
                                    <div className="text-[10px] text-cyan-300 uppercase font-bold">{voterName}</div>
                                    <div className="flex gap-2">
                                        <span className={`text-xs px-2 py-0.5 rounded font-semibold ${
                                            voterResult.status === "VERIFIED" ? "bg-green-900 text-green-300" :
                                            voterResult.status === "REFUTED" ? "bg-red-900 text-red-300" :
                                            voterResult.status === "PLAUSIBLE" ? "bg-yellow-900 text-yellow-300" :
                                            "bg-gray-700 text-gray-300"
                                        }`}>
                                            {voterResult.status}
                                        </span>
                                        <span className="text-xs font-mono text-gray-300">{Math.round((voterResult.confidence ?? 0) * 100)}%</span>
                                    </div>
                                </div>
                                <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden mb-2">
                                    <div
                                        className={`h-full ${(voterResult.confidence ?? 0) > 0.7 ? 'bg-green-500' : (voterResult.confidence ?? 0) > 0.3 ? 'bg-yellow-500' : 'bg-red-500'}`}
                                        style={{ width: `${(voterResult.confidence ?? 0) * 100}%` }}
                                    />
                                </div>
                                {voterResult.reasoning && (
                                    <p className="text-xs text-gray-400 mb-2">"{voterResult.reasoning}"</p>
                                )}
                                {voterResult.metadata && Object.keys(voterResult.metadata).length > 0 && (
                                    <div className="text-[10px] text-gray-500 bg-gray-800/50 p-2 rounded border border-gray-700/30">
                                        {Object.entries(voterResult.metadata).map(([key, value]) => (
                                            <div key={key} className="flex justify-between gap-2">
                                                <span className="text-gray-400">{key}:</span>
                                                <span className="text-gray-300 font-mono">
                                                    {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                                                </span>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        ))
                    ) : claim.voter_scores && Object.keys(claim.voter_scores).length > 0 ? (
                        // Fallback to voter_scores for backward compatibility
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
                    ) : (
                        <p className="text-xs text-gray-500 italic">No voter analysis available</p>
                    )}
                </div>
            </section>

            <section>
                <h4 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-3">Evidence & Sources</h4>
                <div className="space-y-4">
                    {!Array.isArray(claim.evidence) || claim.evidence.length === 0 ? (
                        <div className="bg-gray-900/60 p-4 rounded-xl border border-gray-700/60 text-sm text-gray-400">
                            No source evidence was retrieved for this claim before timeout/deadline.
                        </div>
                    ) : (
                        claim.evidence.map((ev, i) => (
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
                                    <div className="flex gap-2">
                                        {ev.reliability_score !== undefined && (
                                            <span className="bg-blue-900/30 text-blue-400 text-[10px] px-2 py-0.5 rounded-full border border-blue-800/50">
                                                Reliability: {Math.round(ev.reliability_score * 100)}%
                                            </span>
                                        )}
                                        {ev.support && (
                                            <span className={`text-[10px] px-2 py-0.5 rounded-full border ${
                                                ev.support === "supporting" 
                                                    ? "bg-green-900/30 text-green-400 border-green-800/50"
                                                    : ev.support === "contradicting"
                                                    ? "bg-red-900/30 text-red-400 border-red-800/50"
                                                    : "bg-gray-700/30 text-gray-400 border-gray-600/50"
                                            }`}>
                                                {ev.support}
                                            </span>
                                        )}
                                    </div>
                                </div>
                                <p className="text-gray-400 text-sm leading-relaxed italic">
                                    "{ev.snippet.length > 200 ? ev.snippet.substring(0, 200) + '...' : ev.snippet}"
                                </p>
                                
                                {/* Page Quality Signals */}
                                {ev.page_quality_signals && Object.keys(ev.page_quality_signals).length > 0 && (
                                    <div className="mt-2 text-[10px] text-gray-500 bg-gray-800/50 p-2 rounded border border-gray-700/30 space-y-1">
                                        {ev.page_quality_signals.editable_by_public !== undefined && (
                                            <div><span className="text-gray-400">Public Edit:</span> {ev.page_quality_signals.editable_by_public ? "Yes" : "No"}</div>
                                        )}
                                        {ev.page_quality_signals.editor_expertise_est !== undefined && (
                                            <div><span className="text-gray-400">Expert Level:</span> {Math.round(ev.page_quality_signals.editor_expertise_est * 100)}%</div>
                                        )}
                                        {ev.page_quality_signals.open_editability_score !== undefined && (
                                            <div><span className="text-gray-400">Editability:</span> {Math.round(ev.page_quality_signals.open_editability_score * 100)}%</div>
                                        )}
                                    </div>
                                )}
                            </div>
                        ))
                    )}
                </div>
            </section>

            {Array.isArray(claim.contradicting_evidence) && claim.contradicting_evidence.length > 0 && (
                <section>
                    <h4 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-3">Contradicting Evidence</h4>
                    <div className="space-y-3">
                        {claim.contradicting_evidence.map((ev, i) => (
                            <div key={`contra-${i}`} className="bg-red-950/20 p-3 rounded-lg border border-red-900/40">
                                <a href={ev.url} target="_blank" rel="noopener noreferrer" className="text-red-300 text-sm font-semibold hover:text-red-200">
                                    {ev.title || ev.url}
                                </a>
                                <p className="text-red-100/80 text-sm mt-1">{ev.snippet?.slice(0, 220)}{ev.snippet?.length > 220 ? '...' : ''}</p>
                            </div>
                        ))}
                    </div>
                </section>
            )}
        </div>
    );
};

export default DetailPanel;
