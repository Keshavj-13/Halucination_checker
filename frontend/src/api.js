const BASE = "http://localhost:8000";

// Hardcoded fallback used when the backend is unreachable
const FALLBACK = {
    total: 3,
    verified: 1,
    plausible: 1,
    hallucinations: 1,
    claims: [
        {
            text: "The Earth orbits the Sun at an average distance of 93 million miles.",
            status: "Verified",
            confidence: 0.92,
            evidence: [
                {
                    title: "NASA Solar System Exploration",
                    snippet: "Earth orbits the Sun at a mean distance of about 93 million miles.",
                    url: "https://solarsystem.nasa.gov",
                    support: "supporting",
                },
            ],
        },
        {
            text: "Machine learning models improve with more data.",
            status: "Plausible",
            confidence: 0.71,
            evidence: [
                {
                    title: "Google AI Blog – Scaling Laws",
                    snippet: "Larger datasets generally lead to improved model performance.",
                    url: "https://ai.googleblog.com",
                    support: "supporting",
                },
            ],
        },
        {
            text: "Python is always the best language for every task.",
            status: "Hallucination",
            confidence: 0.83,
            evidence: [
                {
                    title: "Stack Overflow Survey 2023",
                    snippet: "Python is popular but not universally fastest.",
                    url: "https://survey.stackoverflow.co/2023",
                    support: "weak",
                },
            ],
        },
    ],
};

async function safeFetch(url, options = {}) {
    try {
        const res = await fetch(url, options);
        if (!res.ok) throw new Error("Non-2xx response");
        return await res.json();
    } catch {
        return null;
    }
}

export async function runAudit(document) {
    const data = await safeFetch(`${BASE}/audit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document }),
    });
    return data ?? FALLBACK;
}

export async function loadSample() {
    const data = await safeFetch(`${BASE}/sample`);
    return data ?? FALLBACK;
}
