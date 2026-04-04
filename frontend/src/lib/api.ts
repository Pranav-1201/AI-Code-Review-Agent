const API_BASE = "http://localhost:8000";

const SCAN_TIMEOUT_MS = 5 * 60 * 1000;


// Start Scan
export async function startScan(repoUrl: string): Promise<string> {

  const response = await fetch(`${API_BASE}/scan`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      repo_path: repoUrl,
    }),
  });

  if (!response.ok) {
    throw new Error("Failed to start scan");
  }

  const data = await response.json();

  return data.scan_id;
}


// Poll Scan Progress
export async function getScanStatus(scanId: string): Promise<any> {

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), SCAN_TIMEOUT_MS);

  try {

    const response = await fetch(`${API_BASE}/scan/${scanId}`, {
      signal: controller.signal
    });

    if (!response.ok) {
      throw new Error("Failed to get scan status");
    }

    return await response.json();

  } finally {
    clearTimeout(timeoutId);
  }
}


// Start Scan AND Wait Until Complete
export async function startAndPollScan(repoPath: string, onProgress?: (status: any) => void) {

  const scanId = await startScan(repoPath);

  while (true) {

    const status = await getScanStatus(scanId);

    if (onProgress) {
      onProgress(status);
    }

    if (status.status === "complete") {
      return status.result;
    }

    if (status.status === "error") {
      throw new Error("Scan failed on backend");
    }

    // wait 2 seconds before polling again
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
}