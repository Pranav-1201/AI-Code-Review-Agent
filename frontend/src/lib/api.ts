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

// Start Scan AND Wait Until Complete (with total deadline)
export async function startAndPollScan(
  repoPath: string,
  onProgress?: (status: any) => void
) {
  const scanId = await startScan(repoPath);
  const deadline = Date.now() + SCAN_TIMEOUT_MS;

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