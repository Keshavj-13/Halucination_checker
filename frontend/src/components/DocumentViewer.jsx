import React from 'react';

const DocumentViewer = ({ text, claims, onSelectClaim, selectedClaim }) => {
    if (!text) return null;

    // Sort claims by start index to process them in order
    const sortedClaims = [...claims].sort((a, b) => a.start_idx - b.start_idx);

    const renderContent = () => {
        let lastIdx = 0;
        const elements = [];

        sortedClaims.forEach((claim, i) => {
            // Add text before the claim
            if (claim.start_idx > lastIdx) {
                elements.push(
                    <span key={`text-${i}`}>
                        {text.substring(lastIdx, claim.start_idx)}
                    </span>
                );
            }

            // Determine color based on status
            const colorClass =
                claim.status === "Verified" ? "border-b-2 border-green-500 bg-green-500/10" :
                    claim.status === "Hallucination" ? "border-b-2 border-red-500 bg-red-500/10" :
                        "border-b-2 border-yellow-500 bg-yellow-500/10";

            const isSelected = selectedClaim && selectedClaim.start_idx === claim.start_idx;

            // Add the highlighted claim
            elements.push(
                <span
                    key={`claim-${i}`}
                    onClick={() => onSelectClaim(claim)}
                    className={`${colorClass} cursor-pointer transition-all hover:brightness-125 ${isSelected ? 'ring-2 ring-blue-500 ring-offset-2 ring-offset-gray-900 rounded-sm' : ''}`}
                    title={`${claim.status} (${Math.round(claim.confidence * 100)}%)`}
                >
                    {text.substring(claim.start_idx, claim.end_idx)}
                </span>
            );

            lastIdx = claim.end_idx;
        });

        // Add remaining text
        if (lastIdx < text.length) {
            elements.push(
                <span key="text-end">
                    {text.substring(lastIdx)}
                </span>
            );
        }

        return elements;
    };

    return (
        <div className="bg-gray-900 rounded-2xl p-8 shadow-2xl border border-gray-800 leading-relaxed text-gray-200 text-lg font-serif whitespace-pre-wrap">
            {renderContent()}
        </div>
    );
};

export default DocumentViewer;
