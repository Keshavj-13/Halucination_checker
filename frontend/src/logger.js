const STORAGE_KEY = "samsa-audit-logs";
const MAX_LOG_ENTRIES = 200;

function serialiseMetadata(metadata) {
    if (metadata === undefined) {
        return undefined;
    }

    try {
        return JSON.parse(JSON.stringify(metadata));
    } catch {
        return { note: "metadata could not be serialized" };
    }
}

function persistLogEntry(entry) {
    if (typeof window === "undefined") {
        return;
    }

    try {
        const existing = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "[]");
        const next = [...existing, entry].slice(-MAX_LOG_ENTRIES);
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
        // Ignore storage failures and keep console logging available.
    }
}

export function createLogger(scope) {
    function write(level, message, metadata) {
        const entry = {
            timestamp: new Date().toISOString(),
            level,
            scope,
            message,
            metadata: serialiseMetadata(metadata),
        };

        persistLogEntry(entry);

        const consoleMethod =
            level === "error" ? console.error : level === "warn" ? console.warn : console.log;

        if (entry.metadata !== undefined) {
            consoleMethod(`[${entry.timestamp}] [${scope}] ${message}`, entry.metadata);
            return;
        }

        consoleMethod(`[${entry.timestamp}] [${scope}] ${message}`);
    }

    return {
        info: (message, metadata) => write("info", message, metadata),
        warn: (message, metadata) => write("warn", message, metadata),
        error: (message, metadata) => write("error", message, metadata),
    };
}
