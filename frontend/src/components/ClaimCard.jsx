import { useState } from "react";

const STATUS_STYLES = {
    Verified: "bg-green-900 text-green-300 border border-green-700",
    Plausible: "bg-yellow-900 text-yellow-300 border border-yellow-700",
    Hallucination: "bg-red-900 text-red-300 border border-red-700",
    VERIFIED: "bg-green-900 text-green-300 border border-green-700",
    PLAUSIBLE: "bg-yellow-900 text-yellow-300 border border-yellow-700",
    REFUTED: "bg-red-900 text-red-300 border border-red-700",
    UNCERTAIN: "bg-gray-700 text-gray-300 border border-gray-600",
    CONFLICTING: "bg-orange-900 text-orange-300 border border-orange-700",
};

const BAR_COLOR = {
    Verified: "bg-green-500",
    Plausible: "bg-yellow-500",
    Hallucination: "bg-red-500",
    VERIFIED: "bg-green-500",
    PLAUSIBLE: "bg-yellow-500",
    REFUTED: "bg-red-500",
    UNCERTAIN: "bg-gray-600",
    CONFLICTING: "bg-orange-500",
};

export default function ClaimCard({ claim, index }) {
    const [open, setOpen] = useState(false);
    const [showVoters, setShowVoters] = useState(false);
    
    const { text, status, label, confidence, evidence, voter_results } = claim;
    const displayStatus = label || status;
    const pct = Math.round(confidence * 100);

    return (
        <div className="bg-gray-800 rounded-xl p-5 shadow mb-4">
            {/* Header row */}
            <div className="flex items-start justify-between gap-4">
                <p className="text-gray-100 text-sm leading-relaxed flex-1">
                    <span className="text-gray-500 font-mono mr-2">#{index + 1}</span>
                    {text}
                </p>
                <span className={`text-xs font-semibold px-2 py-1 rounded-full shrink-0 ${STATUS_STYLES[displayStatus] || STATUS_STYLES.PLAUSIBLE}`}>
                    {displayStatus}
                </span>
            </div>

            {/* Confidence bar */}
            <div className="mt-3">
                <div className="flex justify-between text-xs text-gray-400 mb-1">
                    <span>Confidence</span>
                    <span>{pct}%</span>
                </div>
                <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
                    <div
                        className={`h-full rounded-full transition-all ${BAR_COLOR[displayStatus] || BAR_COLOR.PLAUSIBLE}`}
                        style={{ width: `${pct}%` }}
                    />
                </div>
            </div>

            {/* Voter results summary (if available) */}
            {voter_results && Object.keys(voter_results).length > 0 && (
                <button
                    onClick={() => setShowVoters(!showVoters)}
                    className="mt-3 text-xs text-cyan-400 hover:text-cyan-300 transition-colors"
                >
                    {showVoters ? "▲ Hide voter analysis" : "▼ Show voter analysis"} ({Object.keys(voter_results).length})
                </button>
            )}

            {showVoters && voter_results && Object.keys(voter_results).length > 0 && (
                <div className="mt-3 space-y-2 bg-gray-900/30 rounded-lg p-3 border border-gray-700/30">
                    {Object.entries(voter_results).map(([voterName, voterResult]) => (
                        <div key={voterName} className="bg-gray-800/50 rounded p-2 border border-gray-700/50">
                            <div className="flex items-center justify-between gap-2">
                                <span className="text-xs font-semibold text-cyan-300">{voterName}</span>
                                <span className={`text-xs px-1.5 py-0.5 rounded ${
                                    voterResult.status === "VERIFIED" ? "bg-green-900 text-green-300" :
                                    voterResult.status === "REFUTED" ? "bg-red-900 text-red-300" :
                                    voterResult.status === "PLAUSIBLE" ? "bg-yellow-900 text-yellow-300" :
                                    "bg-gray-700 text-gray-300"
                                }`}>
                                    {voterResult.confidence ? Math.round(voterResult.confidence * 100) + "%" : "—"}
                                </span>
                            </div>
                            {voterResult.reasoning && (
                                <p className="text-xs text-gray-400 mt-1">{voterResult.reasoning}</p>
                            )}
                        </div>
                    ))}
                </div>
            )}

            {/* Expandable evidence */}
            <button
                onClick={() => setOpen(!open)}
                className="mt-3 text-xs text-gray-400 hover:text-gray-200 transition-colors"
            >
                {open ? "▲ Hide evidence" : "▼ Show evidence"} ({evidence?.length || 0})
            </button>

            {open && evidence && evidence.length > 0 && (
                <div className="mt-3 space-y-3">
                    {evidence.map((ev, i) => (
                        <div key={i} className="bg-gray-750 border border-gray-700 rounded-lg p-3">
                            <div className="flex items-center justify-between gap-2 mb-1">
                                <p className="text-xs font-semibold text-gray-200">{ev.title}</p>
                                <div className="flex gap-1">
                                    <span className={`text-xs px-1.5 py-0.5 rounded ${ev.support === "supporting"
                                            ? "bg-green-900 text-green-300"
                                            : ev.support === "contradicting"
                                            ? "bg-red-900 text-red-300"
                                            : "bg-gray-700 text-gray-400"
                                        }`}>
                                        {ev.support}
                                    </span>
                                    {ev.reliability_score !== undefined && (
                                        <span className="text-xs px-1.5 py-0.5 rounded bg-blue-900 text-blue-300">
                                            Reliability: {Math.round(ev.reliability_score * 100)}%
                                        </span>
                                    )}
                                </div>
                            </div>
                            <p className="text-xs text-gray-400 italic mb-1">"{ev.snippet}"</p>
                            
                            {/* Page quality signals */}
                            {ev.page_quality_signals && Object.keys(ev.page_quality_signals).length > 0 && (
                                <div className="text-xs text-gray-500 mb-2 space-y-1">
                                    {ev.page_quality_signals.editable_by_public !== undefined && (
                                        <div>Public Edit: {ev.page_quality_signals.editable_by_public ? "Yes" : "No"}</div>
                                    )}
                                    {ev.page_quality_signals.editor_expertise_est !== undefined && (
                                        <div>Expert Level: {Math.round(ev.page_quality_signals.editor_expertise_est * 100)}%</div>
                                    )}
                                    {ev.page_quality_signals.open_editability_score !== undefined && (
                                        <div>Editability: {Math.round(ev.page_quality_signals.open_editability_score * 100)}%</div>
                                    )}
                                </div>
                            )}
                            
                            <a
                                href={ev.url}
                                target="_blank"
                                rel="noreferrer"
                                className="text-xs text-blue-400 hover:underline break-all"
                            >
                                {ev.url}
                            </a>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
