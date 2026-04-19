function resolveApiBase() {
    const configured = (import.meta.env.VITE_API_BASE || "").trim();
    if (configured) {
        return configured.replace(/\/$/, "");
    }

    const host = window.location.hostname;
    const port = window.location.port;
    const isLocal = host === "localhost" || host === "127.0.0.1";
    const isLikelyVitePort = port === "5173" || port === "4173" || port === "3000";

    // Local frontend dev commonly runs on 5173 while backend runs on 8000.
    if (isLocal && isLikelyVitePort) {
        return "http://127.0.0.1:8000";
    }

    return window.location.origin.replace(/\/$/, "");
}

const BASE = resolveApiBase();

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

function buildUrl(path) {
    return `${BASE}${path}`;
}

function buildHeaders({ token, json = false } = {}) {
    const headers = {};
    if (json) {
        headers["Content-Type"] = "application/json";
    }

    if (token) {
        headers.Authorization = `Bearer ${token}`;
    }

    return headers;
}

function tryParseJson(text) {
    if (!text) {
        return null;
    }

    try {
        return JSON.parse(text);
    } catch {
        return null;
    }
}

async function readError(response) {
    const text = await response.text();
    const payload = tryParseJson(text);
    if (payload && typeof payload === "object") {
        if (typeof payload.detail === "string") {
            return payload.detail;
        }

        if (typeof payload.message === "string") {
            return payload.message;
        }

        return JSON.stringify(payload);
    }

    return text || `${response.status} ${response.statusText}`;
}

async function requestJson(path, { method = "GET", body, token, signal } = {}) {
    const isFormData = body instanceof FormData;
    let response;
    try {
        response = await fetch(buildUrl(path), {
            method,
            headers: buildHeaders({ token, json: body !== undefined && !isFormData }),
            body:
                body === undefined
                    ? undefined
                    : isFormData
                        ? body
                        : JSON.stringify(body),
            signal,
        });
    } catch (error) {
        if (error?.name === "AbortError") {
            throw error;
        }
        throw new Error(`Could not reach API at ${BASE}. Start backend or set VITE_API_BASE.`);
    }

    if (!response.ok) {
        throw new Error(await readError(response));
    }

    if (response.status === 204) {
        return null;
    }

    const text = await response.text();
    if (!text) {
        return null;
    }

    const payload = tryParseJson(text);
    if (payload === null) {
        throw new Error("Expected a JSON response from the server.");
    }

    return payload;
}

async function safeFetch(path, options = {}) {
    try {
        return await requestJson(path, options);
    } catch {
        return null;
    }
}

export function login(credentials) {
    return requestJson("/auth/login", {
        method: "POST",
        body: credentials,
    });
}

export function register(credentials) {
    return requestJson("/auth/register", {
        method: "POST",
        body: credentials,
    });
}

export function getCurrentUser(token) {
    return requestJson("/auth/me", { token });
}

export function logout(token) {
    return requestJson("/auth/logout", {
        method: "POST",
        token,
    });
}

export function listHistory(token) {
    return requestJson("/history", { token });
}

export function getHistoryDetail(historyId, token) {
    return requestJson(`/history/${historyId}`, { token });
}

export function sendChatMessage(payload, token) {
    return requestJson("/chat", {
        method: "POST",
        body: payload,
        token,
    });
}

export function getChatHistory(sessionId, token) {
    return requestJson(`/chat/history/${encodeURIComponent(sessionId)}`, { token });
}

export async function runAudit(document, token) {
    const data = await safeFetch("/audit", {
        method: "POST",
        body: { document },
        token,
    });
    return data ?? FALLBACK;
}

export async function extractTextFromDocument(formData, token) {
    return await safeFetch("/documents/readable-text", {
        method: "POST",
        body: formData,
        token,
    });
}

export async function runAuditStream(document, onUpdate, token, signal) {
    try {
        const response = await fetch(buildUrl("/audit/stream"), {
            method: "POST",
            headers: buildHeaders({ token, json: true }),
            body: JSON.stringify({ document }),
            signal,
        });

        if (!response.ok) throw new Error(await readError(response));

        if (!response.body) {
            throw new Error("Stream body is empty");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let terminalSeen = false;

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n\n");
            buffer = lines.pop();

            for (const line of lines) {
                if (line.startsWith("data: ")) {
                    const data = JSON.parse(line.replace("data: ", ""));
                    if (data.type === "done" || data.type === "error") {
                        terminalSeen = true;
                    }
                    onUpdate(data);
                }
            }
        }

        if (!terminalSeen) {
            onUpdate({ type: "stream_end" });
        }
    } catch (err) {
        if (err?.name === "AbortError") {
            onUpdate({ type: "cancelled", message: "Request cancelled" });
            return;
        }
        console.error("Streaming error:", err);
        onUpdate({ type: "error", message: err.message });
    }
}

export async function loadSample() {
    const data = await safeFetch("/audit/sample");
    return data ?? FALLBACK;
}
