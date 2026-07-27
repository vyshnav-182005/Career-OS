export interface OptimizationResponse {
  success: boolean;
  message: string;
  data?: {
    workflow_id?: string;
    status?: string;
    html_content?: string;
    pdf_content?: string;
  };
}

export interface WorkflowStatusResponse {
  workflow_id: string;
  status: "queued" | "running" | "succeeded" | "failed" | "timed_out";
  message: string;
  data?: {
    html_content?: string;
    pdf_content?: string;
  };
}

const TERMINAL_STATUSES = new Set(["succeeded", "failed", "timed_out"]);

function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function getResumeOptimizationStatus(workflowId: string): Promise<WorkflowStatusResponse> {
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";

  const response = await fetch(`${backendUrl}/workflows/${workflowId}`, {
    method: "GET",
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch workflow status: ${response.statusText}`);
  }

  return response.json();
}

async function waitForResumeOptimization(
  workflowId: string,
  onStatus?: (status: WorkflowStatusResponse) => void,
): Promise<OptimizationResponse> {
  const startedAt = Date.now();
  const maxWaitMs = 5 * 60 * 1000;

  while (Date.now() - startedAt < maxWaitMs) {
    const status = await getResumeOptimizationStatus(workflowId);
    onStatus?.(status);

    if (TERMINAL_STATUSES.has(status.status)) {
      return {
        success: status.status === "succeeded",
        message: status.message,
        data: status.data,
      };
    }

    await delay(2000);
  }

  throw new Error("Resume optimization is still running. Please check back shortly.");
}

export async function optimizeResume(
  userId: string,
  jobTitle: string,
  jobDescription: string,
  onStatus?: (status: WorkflowStatusResponse) => void,
): Promise<OptimizationResponse> {
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";
  
  const response = await fetch(`${backendUrl}/workflows/resume-optimize`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      user_id: userId,
      job_title: jobTitle,
      job_description: jobDescription,
    }),
  });

  if (!response.ok) {
    throw new Error(`Failed to optimize resume: ${response.statusText}`);
  }

  const queued: OptimizationResponse = await response.json();
  const workflowId = queued.data?.workflow_id;

  if (!workflowId) {
    throw new Error("Resume optimization did not return a workflow id.");
  }

  onStatus?.({
    workflow_id: workflowId,
    status: "queued",
    message: queued.message,
    data: queued.data,
  });

  return waitForResumeOptimization(workflowId, onStatus);
}
