import type { PipelineResponse } from "@/lib/types/resume";

/**
 * Sends a resume file (PDF or DOCX) to the Next.js API route
 * which then spawns the Python pipeline.
 */
export async function parseResume(file: File): Promise<PipelineResponse> {
  const parserUrl = `/api/parse-resume`;

  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(parserUrl, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    let detail = `Server error: ${response.status}`;
    try {
      const errBody = await response.json();
      if (errBody.error) detail = errBody.error;
    } catch {
      // ignore JSON parse errors on error responses
    }
    throw new Error(detail);
  }

  return response.json() as Promise<PipelineResponse>;
}
