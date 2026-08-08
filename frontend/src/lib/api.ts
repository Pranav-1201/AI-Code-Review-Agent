const API_BASE = "http://localhost:8000";
const SCAN_TIMEOUT_MS = 5 * 60 * 1000; // total scan deadline
const POLL_REQUEST_TIMEOUT_MS = 15_000;  // per-request timeout (15s)

// Helper: extract a readable error from a failed response
async function extractErrorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return body?.detail || body?.message || body?.error || `HTTP ${response.status}`;
  } catch {
    return `HTTP ${response.status} ${response.statusText}`;
  }
}

// Start Scan
export async function startScan(repoUrl: string): Promise<string> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE}/scan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo_path: repoUrl }),
    });
  } catch (networkErr) {
    // Server not reachable at all
    throw new Error(
      `Cannot reach backend at ${API_BASE}. Is it running? (${(networkErr as Error).message})`
    );
  }

  if (!response.ok) {
    const reason = await extractErrorMessage(response);
    throw new Error(`Failed to start scan: ${reason}`);
  }

  const data = await response.json();

  if (!data?.scan_id) {
    throw new Error("Backend did not return a scan_id. Check your /scan endpoint response shape.");
  }

  return data.scan_id;
}

// Poll Scan Progress (with per-request timeout)
export async function getScanStatus(scanId: string): Promise<any> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), POLL_REQUEST_TIMEOUT_MS);

  let response: Response;

  try {
    response = await fetch(`${API_BASE}/scan/${scanId}`, {
      signal: controller.signal,
    });
  } catch (err: any) {
    if (err?.name === "AbortError") {
      throw new Error(`Poll request timed out after ${POLL_REQUEST_TIMEOUT_MS / 1000}s`);
    }
    throw new Error(`Network error while polling: ${err.message}`);
  } finally {
    clearTimeout(timeoutId);
  }

  if (!response.ok) {
    const reason = await extractErrorMessage(response);
    throw new Error(`Failed to get scan status: ${reason}`);
  }

  return response.json();
}

// Poll a scan to completion against a total deadline. Shared by the SSE
// fallback and the legacy startAndPollScan wrapper.
async function pollScanResult(
  scanId: string,
  onProgress?: (status: any) => void,
  deadline: number = Date.now() + SCAN_TIMEOUT_MS
) {
  while (true) {
    if (Date.now() > deadline) {
      throw new Error(`Scan timed out after ${SCAN_TIMEOUT_MS / 60_000} minutes`);
    }

    const status = await getScanStatus(scanId);

    if (onProgress) onProgress(status);

    if (status.status === "complete") return status.result;

    if (status.status === "error") {
      throw new Error(`Scan failed on backend: ${status.error ?? "unknown reason"}`);
    }

    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
}

// Start Scan AND Wait Until Complete via polling. Kept for backward
// compatibility and used as the SSE fallback path below.
export async function startAndPollScan(
  repoPath: string,
  onProgress?: (status: any) => void
) {
  const scanId = await startScan(repoPath);
  return pollScanResult(scanId, onProgress);
}

// Subscribe to a scan over Server-Sent Events (Item E). One long-lived
// connection replaces 2s polling. On ANY failure — no EventSource in the
// runtime, a proxy that strips the stream, or a backend without the endpoint
// (404) — we transparently fall back to polling the same scan_id, so behaviour
// is never worse than before. Each SSE frame is the same dict shape that
// getScanStatus returns, so downstream handling is identical.
function streamScanResult(
  scanId: string,
  onProgress?: (status: any) => void
): Promise<any> {
  const deadline = Date.now() + SCAN_TIMEOUT_MS;

  // No EventSource (very old runtime / SSR) → poll.
  if (typeof EventSource === "undefined") {
    return pollScanResult(scanId, onProgress, deadline);
  }

  return new Promise((resolve, reject) => {
    const es = new EventSource(`${API_BASE}/scan/${scanId}/stream`);
    let settled = false;

    const deadlineTimer = setTimeout(() => {
      if (settled) return;
      settled = true;
      es.close();
      reject(new Error(`Scan timed out after ${SCAN_TIMEOUT_MS / 60_000} minutes`));
    }, SCAN_TIMEOUT_MS);

    const settle = (fn: () => void) => {
      if (settled) return;
      settled = true;
      clearTimeout(deadlineTimer);
      es.close();
      fn();
    };

    es.onmessage = (evt: MessageEvent) => {
      let status: any;
      try {
        status = JSON.parse(evt.data);
      } catch {
        return; // ignore an unparsable frame
      }

      if (onProgress) onProgress(status);

      if (status.status === "complete") {
        settle(() => resolve(status.result));
      } else if (status.status === "error") {
        settle(() =>
          reject(new Error(`Scan failed on backend: ${status.error ?? "unknown reason"}`))
        );
      }
    };

    es.onerror = () => {
      // Connection error before a terminal frame (endpoint missing, proxy
      // dropped the stream, transient network). EventSource would auto-retry,
      // but we close it and fall back to polling from the same scan_id —
      // idempotent, it just reads state. A benign post-close error that fires
      // after a terminal frame is ignored because `settled` is already true.
      if (settled) return;
      settled = true;
      clearTimeout(deadlineTimer);
      es.close();
      pollScanResult(scanId, onProgress, deadline).then(resolve, reject);
    };
  });
}

// Start Scan AND stream progress to completion (SSE, with polling fallback).
export async function startAndStreamScan(
  repoPath: string,
  onProgress?: (status: any) => void
) {
  const scanId = await startScan(repoPath);
  return streamScanResult(scanId, onProgress);
}

// List past completed scans (persisted history — survives a page reload).
// Returns the raw backend rows: { id, repo, timestamp, health_score,
// files_analyzed, issues_found }. Callers map these to ScanHistoryItem.
export async function listScans(): Promise<any[]> {
  const response = await fetch(`${API_BASE}/scans`);

  if (!response.ok) {
    throw new Error(`Failed to list scans: ${await extractErrorMessage(response)}`);
  }

  const data = await response.json();
  return Array.isArray(data) ? data : (data.scans || []);
}