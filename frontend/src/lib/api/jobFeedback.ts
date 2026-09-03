export type JobFeedbackVote = "up" | "down";

export async function submitJobFeedback(jobId: string, vote: JobFeedbackVote): Promise<void> {
  const response = await fetch(`/api/jobs/${jobId}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ vote }),
  });

  if (!response.ok) {
    let message = `Failed to record feedback: ${response.statusText}`;
    try {
      const data = await response.json();
      message = data.message || data.detail || message;
    } catch {
      // Body wasn't JSON — keep the status-based message.
    }
    throw new Error(message);
  }
}
