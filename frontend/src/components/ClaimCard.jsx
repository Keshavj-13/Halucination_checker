import { useState } from "react";

const STATUS_STYLES = {
    Verified: "bg-green-900 text-green-300 border border-green-700",
    Plausible: "bg-yellow-900 text-yellow-300 border border-yellow-700",
    Hallucination: "bg-red-900 text-red-300 border border-red-700",
};

const BAR_COLOR = {
    Verified: "bg-green-500",
    Plausible: "bg-yellow-500",
    Hallucination: "bg-red-500",
};

export default function ClaimCard({ claim, index }) {
    const [open, setOpen] = useState(false);
    const { text, status, confidence, evidence } = claim;
    const pct = Math.round(confidence * 100);

    return (
        <div className="bg-gray-800 rounded-xl p-5 shadow mb-4">
            {/* Header row */}
            <div className="flex items-start justify-between gap-4">
                <p className="text-gray-100 text-sm leading-relaxed flex-1">
                    <span className="text-gray-500 font-mono mr-2">#{index + 1}</span>
                    {text}
                </p>
                <span className={`text-xs font-semibold px-2 py-1 rounded-full shrink-0 ${STATUS_STYLES[status]}`}>
                    {status}
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
                        className={`h-full rounded-full transition-all ${BAR_COLOR[status]}`}
                        style={{ width: `${pct}%` }}
                    />
                </div>
            </div>

            {/* Expandable evidence */}
            <button
                onClick={() => setOpen(!open)}
                className="mt-3 text-xs text-gray-400 hover:text-gray-200 transition-colors"
            >
                {open ? "▲ Hide evidence" : "▼ Show evidence"} ({evidence.length})
            </button>

            {open && (
                <div className="mt-3 space-y-3">
                    {evidence.map((ev, i) => (
                        <div key={i} className="bg-gray-750 border border-gray-700 rounded-lg p-3">
                            <div className="flex items-center justify-between gap-2 mb-1">
                                <p className="text-xs font-semibold text-gray-200">{ev.title}</p>
                                <span className={`text-xs px-1.5 py-0.5 rounded ${ev.support === "supporting"
                                        ? "bg-green-900 text-green-300"
                                        : "bg-gray-700 text-gray-400"
                                    }`}>
                                    {ev.support}
                                </span>
                            </div>
                            <p className="text-xs text-gray-400 italic mb-1">"{ev.snippet}"</p>
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
