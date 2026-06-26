import type { ParseResponse } from "@/lib/types/resume";

/**
 * Sends a resume file (PDF or DOCX) to the resume parser microservice
 * and returns the structured ParseResponse.
 */
export async function parseResume(file: File): Promise<ParseResponse> {
  const parserUrl = `${process.env.NEXT_PUBLIC_APP_URL ?? ''}/api/parse-resume`;
  // Ensure the URL is set; fallback to relative path if env not defined
  if (!parserUrl) {
    throw new Error("Resume parser API URL is not configured.");
  }

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
      if (errBody.detail) detail = errBody.detail;
    } catch {
      // ignore JSON parse errors on error responses
    }
    throw new Error(detail);
  }

  return response.json() as Promise<ParseResponse>;
}
