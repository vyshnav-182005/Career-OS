import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { spawn } from "child_process";
import { writeFile, unlink } from "fs/promises";
import { existsSync } from "fs";
import { tmpdir } from "os";
import path from "path";
import { randomUUID } from "crypto";

/** Maximum file size: 10 MB */
const MAX_FILE_SIZE = 10 * 1024 * 1024;

/** Subprocess timeout: 300 seconds (5 minutes) */
const SUBPROCESS_TIMEOUT_MS = 300_000;

export const maxDuration = 300;

/** Allowed MIME types */
const ALLOWED_TYPES = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);

/**
 * Detect content type from the file's MIME type and extension.
 * Returns "pdf" or "docx", or null if unsupported.
 */
function detectContentType(
  mimeType: string,
  filename: string
): string | null {
  if (
    mimeType === "application/pdf" ||
    filename.toLowerCase().endsWith(".pdf")
  ) {
    return "pdf";
  }
  if (
    mimeType ===
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
    filename.toLowerCase().endsWith(".docx")
  ) {
    return "docx";
  }
  return null;
}

export async function POST(request: NextRequest) {
  /* ── 1. Authenticate ─────────────────────────────────────────── */
  const supabase = await createClient();
  const {
    data: { user },
    error: authError,
  } = await supabase.auth.getUser();

  if (authError || !user) {
    return NextResponse.json(
      { success: false, error: "Unauthorized" },
      { status: 401 }
    );
  }

  /* ── 2. Validate FormData ────────────────────────────────────── */
  let formData: FormData;
  try {
    formData = await request.formData();
  } catch {
    return NextResponse.json(
      { success: false, error: "Invalid form data" },
      { status: 400 }
    );
  }

  const file = formData.get("file");
  if (!file || !(file instanceof File)) {
    return NextResponse.json(
      { success: false, error: "No file provided" },
      { status: 400 }
    );
  }

  const contentType = detectContentType(file.type, file.name);
  // Map the short type to the MIME type expected by the Python parser
  const mimeContentType = contentType === "pdf"
    ? "application/pdf"
    : "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  if (!contentType) {
    return NextResponse.json(
      {
        success: false,
        error: "Unsupported file type. Only PDF and DOCX are accepted.",
      },
      { status: 400 }
    );
  }

  if (file.size > MAX_FILE_SIZE) {
    return NextResponse.json(
      { success: false, error: "File exceeds 10 MB limit." },
      { status: 400 }
    );
  }

  /* ── 3. Write to temp file ───────────────────────────────────── */
  const ext = contentType === "pdf" ? ".pdf" : ".docx";
  const tempFilePath = path.join(tmpdir(), `resume-${randomUUID()}${ext}`);

  try {
    const arrayBuffer = await file.arrayBuffer();
    await writeFile(tempFilePath, Buffer.from(arrayBuffer));
  } catch (err) {
    console.error("Failed to write temp file:", err);
    return NextResponse.json(
      { success: false, error: "Failed to process uploaded file." },
      { status: 500 }
    );
  }

  /* ── 4. Spawn Python subprocess ──────────────────────────────── */
  // process.cwd() is the frontend dir in Next.js dev mode
  const projectRoot = path.resolve(process.cwd(), "..");
  const venvPython = path.join(projectRoot, "venv", "Scripts", "python.exe");
const pythonExe = process.env.PYTHON_EXECUTABLE ?? (existsSync(venvPython) ? venvPython : "python");
  const scriptPath = path.join(
    projectRoot,
    "services",
    "resume-parser",
    "run_pipeline.py"
  );

  const subprocessEnv: Record<string, string> = {
    ...Object.fromEntries(
      Object.entries(process.env).filter(
        (entry): entry is [string, string] => entry[1] !== undefined
      )
    ),
    NVIDIA_API_KEY: process.env.NVIDIA_API_KEY ?? "",
    SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
    SUPABASE_SERVICE_KEY: process.env.SUPABASE_SERVICE_KEY ?? "",
  };

  try {
    const result = await runPythonPipeline(
      pythonExe,
      scriptPath,
      [tempFilePath, mimeContentType, user.id],
      subprocessEnv
    );

    /* ── 5. Parse stdout as JSON ─────────────────────────────── */
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(result.stdout);
    } catch {
      console.error("Python stdout was not valid JSON:", result.stdout);
      console.error("Python stderr:", result.stderr);
      return NextResponse.json(
        {
          success: false,
          error: "Pipeline returned invalid output.",
        },
        { status: 500 }
      );
    }

    if (result.exitCode !== 0) {
      const errorMsg =
        (parsed.error as string) ||
        result.stderr ||
        "Pipeline exited with an error.";
      return NextResponse.json(
        { success: false, error: errorMsg },
        { status: 500 }
      );
    }

    return NextResponse.json(parsed);
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Pipeline execution failed.";
    console.error("Pipeline error:", message);
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  } finally {
    /* ── 6. Cleanup temp file ──────────────────────────────────── */
    try {
      await unlink(tempFilePath);
    } catch {
      // best-effort cleanup
    }
  }
}

/* ── Helper: run Python as a child process with timeout ──────────── */
interface PipelineResult {
  stdout: string;
  stderr: string;
  exitCode: number;
}

function runPythonPipeline(
  pythonExe: string,
  scriptPath: string,
  args: string[],
  env: Record<string, string>
): Promise<PipelineResult> {
  return new Promise((resolve, reject) => {
    const child: any = spawn(pythonExe, [scriptPath, ...args], { env: env as any });

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString();
    });

    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString();
    });

    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      console.error("Timeout reached. stdout:", stdout, "stderr:", stderr);
      reject(new Error("Pipeline timed out after 300 seconds."));
    }, SUBPROCESS_TIMEOUT_MS);

    child.on("close", (code: number | null) => {
      clearTimeout(timer);
      resolve({ stdout, stderr, exitCode: code ?? 1 });
    });

    child.on("error", (err: Error) => {
      clearTimeout(timer);
      reject(
        new Error(`Failed to start pipeline: ${err.message}`)
      );
    });
  });
}
