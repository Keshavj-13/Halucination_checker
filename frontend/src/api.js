const BASE = "http://localhost:8000";

const FALLBACK = {
    document:
        "The Earth orbits the Sun. Python is best. AI is magic.",
    total: 3,
    verified: 1,
    plausible: 1,
    hallucinations: 1,
    claims: [
        { text: "The Earth orbits the Sun.", status: "Verified", confidence: 0.92, start_idx: 0, end_idx: 24, evidence: [] },
        { text: "Python is best.", status: "Plausible", confidence: 0.71, start_idx: 25, end_idx: 40, evidence: [] },
        { text: "AI is magic.", status: "Hallucination", confidence: 0.83, start_idx: 41, end_idx: 53, evidence: [] },
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

export async function runAuditStream(input, onUpdate) {
    const isFile = input instanceof FormData;
    const url = isFile ? `${BASE}/audit/upload/stream` : `${BASE}/audit/stream`;
    
    const options = {
        method: "POST",
    };
    
    if (isFile) {
        options.body = input;  // FormData
    } else {
        options.headers = { "Content-Type": "application/json" };
        options.body = JSON.stringify({ document: input });
    }

    try {
        const response = await fetch(url, options);

        if (!response.ok) throw new Error("Stream failed");

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n\n");
            buffer = lines.pop();

            for (const line of lines) {
                if (line.startsWith("data: ")) {
                    const data = JSON.parse(line.replace("data: ", ""));
                    onUpdate(data);
                }
            }
        }
    } catch (err) {
        console.error("Streaming error:", err);
        onUpdate({ type: "error", message: err.message });
    }
}

export async function loadSample() {
    const data = await safeFetch(`${BASE}/audit/sample`);
    return data ?? FALLBACK;
}
