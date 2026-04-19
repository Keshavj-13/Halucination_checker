const BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");

const FALLBACK = {
    document: "The Earth orbits the Sun. Python is best. AI is magic.",
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

async function requestJson(path, { method = "GET", body, token } = {}) {
    const isFormData = body instanceof FormData;
    const response = await fetch(buildUrl(path), {
        method,
        headers: buildHeaders({ token, json: body !== undefined && !isFormData }),
        body:
            body === undefined
                ? undefined
                : isFormData
                  ? body
                  : JSON.stringify(body),
    });

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

export function extractTextFromDocument(formData, token) {
    return requestJson("/documents/readable-text", {
        method: "POST",
        body: formData,
        token,
    });
}

export async function runAudit(document, token) {
    const data = await safeFetch("/audit", {
        token,
        method: "POST",
        body: { document },
    });
    return data ?? FALLBACK;
}

async function runAuditUploadFallback(formData, onUpdate, token) {
    try {
        const response = await fetch(buildUrl("/audit/upload"), {
            method: "POST",
            headers: buildHeaders({ token }),
            body: formData,
        });

        if (!response.ok) {
            throw new Error(await readError(response));
        }

        const data = await response.json();
        onUpdate({ type: "start", total: data.total });

        for (const claim of data.claims) {
            onUpdate({ type: "claim", claim });
        }

        onUpdate({ type: "done" });
        return { type: "done" };
    } catch (err) {
        console.error("Upload fallback error:", err);
        onUpdate({ type: "error", message: err.message });
        return null;
    }
}

export async function runAuditStream(input, onUpdate, token) {
    const isFile = input instanceof FormData;
    const url = isFile ? "/audit/upload/stream" : "/audit/stream";
    const headers = buildHeaders({ token, json: !isFile });

    const options = {
        method: "POST",
        headers,
        body: isFile ? input : JSON.stringify({ document: input }),
    };

    try {
        const response = await fetch(buildUrl(url), options);

        if (!response.ok) {
            throw new Error(await readError(response));
        }

        if (!response.body) {
            throw new Error("Stream body is empty");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let donePayload = null;

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n\n");
            buffer = lines.pop() || "";

            for (const line of lines) {
                if (!line.startsWith("data: ")) {
                    continue;
                }

                const data = JSON.parse(line.replace("data: ", ""));
                if (data.type === "done") {
                    donePayload = data;
                }
                onUpdate(data);
            }
        }

        return donePayload;
    } catch (err) {
        console.error("Streaming error:", err);

        if (isFile) {
            console.warn("Streaming upload failed, falling back to regular file upload.");
            onUpdate({
                type: "status",
                message: "Stream failure detected. Falling back to regular file upload...",
            });
            return runAuditUploadFallback(input, onUpdate, token);
        }

        onUpdate({ type: "error", message: err.message });
        return null;
    }
}

export async function loadSample() {
    const data = await safeFetch("/audit/sample");
    return data ?? FALLBACK;
}
