import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faFileLines,
  faUser,
  faLink,
  faCopy,
  faCheck,
  faArrowLeft,
  faArrowUpRightFromSquare,
  faClock,
  faCircleCheck,
  faCircleXmark,
  faCloudArrowUp,
  faListCheck,
} from "@fortawesome/free-solid-svg-icons";
import Navbar from "../components/Navbar";
import { useChunkedUpload } from "../hooks/useChunkedUpload";
import styles from "./RecruiterPage.module.css";

// Use VITE_API_URL in production (points to Render backend)
const API_ROOT = import.meta.env.VITE_API_URL
  ? String(import.meta.env.VITE_API_URL).replace(/\/$/, "")
  : "";

/* ── Types ─────────────────────────────────────────────── */

interface JdPreview {
  session_id: string;
  job_title: string;
  company: string;
  location: string;
  employment_type: string;
  experience_required: string;
  salary_range: string;
  required_skills: string[];
  nice_to_have_skills: string[];
  responsibilities: string[];
  qualifications: string[];
}

interface ResumePreview {
  session_id: string;
  candidate_name: string;
  candidate_email: string;
  candidate_phone: string;
  current_role: string;
  total_experience_years: number;
  candidate_skills: string[];
  match_score: number;
  match_tier: {
    tier: string;
    label: string;
    color: string;
    description: string;
    icon: string;
  };
  matched_skills: string[];
  missing_skills: string[];
}

interface PrepareResult {
  session_id: string;
  interview_ready: boolean;
  job_title: string;
  candidate_name: string;
  match_score: number;
  max_questions: number;
  context_preview: string;
}

interface SessionSummary {
  session_id: string;
  candidate_name: string;
  job_title: string;
  company: string;
  is_complete: boolean;
  question_count: number;
  max_questions: number;
  match_score: number;
  interview_started_at: number;
  interview_ended_at: number;
  overall_score: number | null;
}

/* ── Component ─────────────────────────────────────────── */

const tierColorMap: Record<string, string> = {
  green: "var(--color-success, #22c55e)",
  blue: "var(--color-info, #3b82f6)",
  yellow: "var(--color-warning, #eab308)",
  red: "var(--color-danger, #ef4444)",
};

const RecruiterPage: React.FC = () => {
  const jdUpload = useChunkedUpload();
  const resumeUpload = useChunkedUpload();

  const [jdFile, setJdFile] = useState<File | null>(null);
  const [jdPreview, setJdPreview] = useState<JdPreview | null>(null);
  const [jdDragOver, setJdDragOver] = useState(false);
  const jdInputRef = useRef<HTMLInputElement>(null);

  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [resumePreview, setResumePreview] = useState<ResumePreview | null>(null);
  const [resumeDragOver, setResumeDragOver] = useState(false);
  const resumeInputRef = useRef<HTMLInputElement>(null);

  const [prepareLoading, setPrepareLoading] = useState(false);
  const [prepareError, setPrepareError] = useState<string | null>(null);
  const [prepareResult, setPrepareResult] = useState<PrepareResult | null>(null);
  const [copied, setCopied] = useState(false);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);

  // Fetch sessions on mount
  useEffect(() => {
    console.log("[Sessions] Fetching from:", `${API_ROOT}/api/recruiter/sessions`);
    fetch(`${API_ROOT}/api/recruiter/sessions`)
      .then((r) => {
        console.log("[Sessions] Response status:", r.status);
        return r.ok ? r.json() : [];
      })
      .then((data: SessionSummary[]) => {
        console.log("[Sessions] Got sessions:", data.length);
        setSessions(data);
      })
      .catch((err) => {
        console.error("[Sessions] Fetch error:", err);
      });
  }, [prepareResult]);

  const extractPdf = (e: React.DragEvent): File | null => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file && file.type === "application/pdf") return file;
    return null;
  };

  /* ── JD Upload ────────────────────────────────────── */

  const uploadJd = useCallback(async (file: File) => {
    setJdFile(file);
    setJdPreview(null);
    setResumePreview(null);
    setPrepareResult(null);
    try {
      const { result } = await jdUpload.upload(file, "jd");
      setJdPreview(result as unknown as JdPreview);
    } catch {
      // error surfaced via jdUpload.error
    }
  }, [jdUpload]);

  /* ── Resume Upload ─────────────────────────────────── */

  const uploadResume = useCallback(async (file: File) => {
    if (!jdPreview) return;
    setResumeFile(file);
    setResumePreview(null);
    setPrepareResult(null);
    try {
      const { result } = await resumeUpload.upload(file, "resume", jdPreview.session_id);
      setResumePreview(result as unknown as ResumePreview);
    } catch {
      // error surfaced via resumeUpload.error
    }
  }, [jdPreview, resumeUpload]);

  /* ── Prepare Interview ─────────────────────────────── */

  const prepareInterview = useCallback(async () => {
    if (!jdPreview) return;
    setPrepareLoading(true);
    setPrepareError(null);
    try {
      const res = await fetch(`${API_ROOT}/api/recruiter/prepare/${jdPreview.session_id}`, { method: "POST" });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Prepare failed (${res.status})`);
      }
      setPrepareResult(await res.json());
    } catch (err: unknown) {
      setPrepareError(err instanceof Error ? err.message : "Prepare failed");
    } finally {
      setPrepareLoading(false);
    }
  }, [jdPreview]);

  const interviewLink = prepareResult
    ? `${window.location.origin}/interview/${prepareResult.session_id}`
    : "";

  const resultsLink = prepareResult
    ? `/results/${prepareResult.session_id}`
    : "";

  const handleCopy = () => {
    navigator.clipboard.writeText(interviewLink).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const resetAll = () => {
    jdUpload.cancel();
    resumeUpload.cancel();
    setJdFile(null); setJdPreview(null);
    setResumeFile(null); setResumePreview(null);
    setPrepareResult(null); setPrepareError(null);
  };

  /* ── Render ────────────────────────────────────────── */
  return (
    <div className="app-container">
      <Navbar />

      <main className={styles.main}>
        {/* ── Page header ──────────────────────────────── */}
        <div className={styles.pageHeader}>
          <div className={styles.pageHeaderLeft}>
            <button type="button" className={styles.backBtn} onClick={resetAll} aria-label="Reset">
              <FontAwesomeIcon icon={faArrowLeft} />
            </button>
            <div>
              <h1 className={styles.pageTitle}>New Pre-Screening Session</h1>
              <p className={styles.pageSub}>Upload JD and Resume to begin</p>
            </div>
          </div>
        </div>

        {/* ── Two-column upload area ───────────────────── */}
        {!prepareResult && (
          <div className={styles.columns}>
            {/* LEFT — Job Description */}
            <div className={styles.uploadCard}>
              <div className={styles.cardHeader}>
                <FontAwesomeIcon icon={faFileLines} className={styles.cardHeaderIcon} />
                <h3 className={styles.cardHeaderTitle}>Job Description</h3>
              </div>

              {!jdPreview ? (
                <>
                  <div
                    className={`${styles.dropZone} ${jdDragOver ? styles.dropZoneActive : ""} ${jdUpload.status !== "idle" && jdUpload.status !== "error" ? styles.dropZoneBusy : ""}`}
                    onDragOver={(e) => { e.preventDefault(); setJdDragOver(true); }}
                    onDragLeave={() => setJdDragOver(false)}
                    onDrop={(e) => { setJdDragOver(false); const f = extractPdf(e); if (f) uploadJd(f); }}
                    onClick={() => { if (jdUpload.status === "idle" || jdUpload.status === "error") jdInputRef.current?.click(); }}
                  >
                    {jdUpload.status === "idle" || jdUpload.status === "error" ? (
                      <>
                        <div className={styles.dropIconWrap}>
                          <FontAwesomeIcon icon={faCloudArrowUp} />
                        </div>
                        <span className={styles.dropTitle}>
                          {jdFile ? jdFile.name : "Drop PDF here"}
                        </span>
                        <span className={styles.dropHint}>or click to browse</span>
                      </>
                    ) : jdUpload.status === "uploading" ? (
                      <div className={styles.progressWrap}>
                        <span className={styles.progressLabel}>Uploading… {jdUpload.progress}%</span>
                        <div className={styles.progressTrack}>
                          <div className={styles.progressBar} style={{ width: `${jdUpload.progress}%` }} />
                        </div>
                        <span className={styles.progressSub}>{jdFile?.name}</span>
                      </div>
                    ) : (
                      <div className={styles.progressWrap}>
                        <span className={styles.analyzeSpinner} />
                        <span className={styles.progressLabel}>
                          {jdUpload.status === "assembling" ? "Assembling…" : "Analyzing JD…"}
                        </span>
                      </div>
                    )}
                    <input ref={jdInputRef} type="file" accept=".pdf" className={styles.hiddenInput}
                      onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadJd(f); }} />
                  </div>
                  {jdUpload.error && <p className={styles.error}>{jdUpload.error}</p>}
                </>
              ) : (
                <div className={styles.analysisResult}>
                  <div className={styles.analysisHeader}>
                    <FontAwesomeIcon icon={faCircleCheck} className={styles.analysisCheckIcon} />
                    <span>Analyzed!</span>
                  </div>
                  <div className={styles.analysisBody}>
                    <div className={styles.analysisRow}>
                      <span className={styles.analysisLabel}>Role</span>
                      <span className={styles.analysisValue}>{jdPreview.job_title || "—"}</span>
                    </div>
                    <div className={styles.analysisRow}>
                      <span className={styles.analysisLabel}>Experience</span>
                      <span className={styles.analysisValue}>{jdPreview.experience_required || "—"}</span>
                    </div>
                    {jdPreview.required_skills.length > 0 && (
                      <div className={styles.analysisTags}>
                        <span className={styles.analysisLabel}>Skills</span>
                        <div className={styles.tags}>
                          {jdPreview.required_skills.map((s) => (
                            <span key={s} className={styles.tag}>{s}</span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* RIGHT — Resume */}
            <div className={styles.uploadCard}>
              <div className={styles.cardHeader}>
                <FontAwesomeIcon icon={faUser} className={styles.cardHeaderIcon} />
                <h3 className={styles.cardHeaderTitle}>Candidate Resume</h3>
              </div>

              {!resumePreview ? (
                <>
                  <div
                    className={`${styles.dropZone} ${resumeDragOver ? styles.dropZoneActive : ""} ${!jdPreview ? styles.dropZoneDisabled : ""} ${resumeUpload.status !== "idle" && resumeUpload.status !== "error" ? styles.dropZoneBusy : ""}`}
                    onDragOver={(e) => { if (jdPreview) { e.preventDefault(); setResumeDragOver(true); } }}
                    onDragLeave={() => setResumeDragOver(false)}
                    onDrop={(e) => { setResumeDragOver(false); if (!jdPreview) return; const f = extractPdf(e); if (f) uploadResume(f); }}
                    onClick={() => { if (jdPreview && (resumeUpload.status === "idle" || resumeUpload.status === "error")) resumeInputRef.current?.click(); }}
                  >
                    {!jdPreview ? (
                      <>
                        <div className={`${styles.dropIconWrap} ${styles.dropIconDisabled}`}>
                          <FontAwesomeIcon icon={faCloudArrowUp} />
                        </div>
                        <span className={styles.dropTitle}>Upload JD first</span>
                      </>
                    ) : resumeUpload.status === "idle" || resumeUpload.status === "error" ? (
                      <>
                        <div className={styles.dropIconWrap}>
                          <FontAwesomeIcon icon={faCloudArrowUp} />
                        </div>
                        <span className={styles.dropTitle}>
                          {resumeFile ? resumeFile.name : "Drop PDF here"}
                        </span>
                        <span className={styles.dropHint}>or click to browse</span>
                      </>
                    ) : resumeUpload.status === "uploading" ? (
                      <div className={styles.progressWrap}>
                        <span className={styles.progressLabel}>Uploading… {resumeUpload.progress}%</span>
                        <div className={styles.progressTrack}>
                          <div className={styles.progressBar} style={{ width: `${resumeUpload.progress}%` }} />
                        </div>
                        <span className={styles.progressSub}>{resumeFile?.name}</span>
                      </div>
                    ) : (
                      <div className={styles.progressWrap}>
                        <span className={styles.analyzeSpinner} />
                        <span className={styles.progressLabel}>
                          {resumeUpload.status === "assembling" ? "Assembling…" : "Analyzing resume…"}
                        </span>
                      </div>
                    )}
                    <input ref={resumeInputRef} type="file" accept=".pdf" className={styles.hiddenInput}
                      onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadResume(f); }} />
                  </div>
                  {resumeUpload.error && <p className={styles.error}>{resumeUpload.error}</p>}
                </>
              ) : (
                <div className={styles.analysisResult}>
                  <div className={styles.analysisHeader}>
                    <FontAwesomeIcon icon={faCircleCheck} className={styles.analysisCheckIcon} />
                    <span>Analyzed!</span>
                  </div>
                  <div className={styles.analysisBody}>
                    <div className={styles.analysisRow}>
                      <span className={styles.analysisLabel}>Name</span>
                      <span className={styles.analysisValue}>{resumePreview.candidate_name}</span>
                    </div>
                    <div className={styles.analysisRow}>
                      <span className={styles.analysisLabel}>Role</span>
                      <span className={styles.analysisValue}>{resumePreview.current_role || "—"} · {resumePreview.total_experience_years} yrs</span>
                    </div>
                    {/* Match tier badge */}
                    {resumePreview.match_tier && (
                      <div className={styles.matchRow}>
                        <span className={styles.analysisLabel}>Match</span>
                        <span
                          className={styles.matchTierBadge}
                          style={{
                            color: tierColorMap[resumePreview.match_tier.color] || "var(--text-primary)",
                            borderColor: tierColorMap[resumePreview.match_tier.color] || "var(--border)",
                          }}
                        >
                          {resumePreview.match_tier.icon} {resumePreview.match_tier.tier}
                        </span>
                      </div>
                    )}
                    {resumePreview.match_tier?.description && (
                      <p className={styles.matchDescription}>{resumePreview.match_tier.description}</p>
                    )}
                    {/* Skills */}
                    {resumePreview.matched_skills.length > 0 && (
                      <div className={styles.analysisTags}>
                        <div className={styles.tags}>
                          {resumePreview.matched_skills.map((s) => (
                            <span key={s} className={`${styles.tag} ${styles.tagMatch}`}>
                              <FontAwesomeIcon icon={faCircleCheck} className={styles.tagIcon} /> {s}
                            </span>
                          ))}
                          {resumePreview.missing_skills.map((s) => (
                            <span key={s} className={`${styles.tag} ${styles.tagMissing}`}>
                              <FontAwesomeIcon icon={faCircleXmark} className={styles.tagIcon} /> {s}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Generate button ──────────────────────────── */}
        {!prepareResult && (
          <div className={styles.generateRow}>
            {prepareError && <p className={styles.error}>{prepareError}</p>}
            <button
              type="button"
              className={styles.generateBtn}
              disabled={!jdPreview || prepareLoading}
              onClick={prepareInterview}
            >
              <FontAwesomeIcon icon={faLink} />
              {prepareLoading ? "Preparing…" : "Generate Interview Link"}
            </button>
          </div>
        )}

        {/* ── Link generated result ────────────────────── */}
        {prepareResult && (
          <div className={styles.linkCard}>
            <div className={styles.linkCardHeader}>
              <FontAwesomeIcon icon={faCircleCheck} className={styles.linkSuccessIcon} />
              <h2 className={styles.linkCardTitle}>Interview Link Generated!</h2>
            </div>

            <div className={styles.linkRow}>
              <input type="text" readOnly value={interviewLink} className={styles.linkInput} />
              <button type="button" className={styles.copyBtn} onClick={handleCopy}>
                <FontAwesomeIcon icon={copied ? faCheck : faCopy} />
                {copied ? "Copied!" : "Copy Link"}
              </button>
            </div>

            <div className={styles.linkActions}>
              <Link to={resultsLink} className={styles.actionBtn}>
                <FontAwesomeIcon icon={faArrowUpRightFromSquare} />
                Open Results Page
              </Link>
              <button type="button" className={styles.actionBtnGhost} onClick={resetAll}>
                New Session
              </button>
            </div>

            <div className={styles.linkExpiry}>
              <FontAwesomeIcon icon={faClock} />
              Link expires in 24 hours
            </div>
          </div>
        )}

        {/* ── Recent Sessions ──────────────────────────── */}
        {sessions.length > 0 && (
          <div className={styles.sessionsCard}>
            <div className={styles.cardHeader}>
              <FontAwesomeIcon icon={faListCheck} className={styles.cardHeaderIcon} />
              <h3 className={styles.cardHeaderTitle}>Recent Sessions</h3>
            </div>
            <div className={styles.sessionsTable}>
              <div className={styles.sessionsHeader}>
                <span>Candidate</span>
                <span>Role</span>
                <span>Status</span>
                <span>Score</span>
                <span></span>
              </div>
              {sessions.map((s) => (
                <div key={s.session_id} className={styles.sessionsRow}>
                  <span className={styles.sessionName}>{s.candidate_name}</span>
                  <span className={styles.sessionRole}>{s.job_title}</span>
                  <span className={`${styles.sessionStatus} ${s.is_complete ? styles.sessionDone : styles.sessionPending}`}>
                    {s.is_complete ? "Complete" : s.question_count > 0 ? "In Progress" : "Pending"}
                  </span>
                  <span className={styles.sessionScore}>
                    {s.overall_score != null ? `${s.overall_score.toFixed(1)}/10` : "—"}
                  </span>
                  <Link to={`/results/${s.session_id}`} className={styles.sessionViewBtn}>
                    View
                  </Link>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

export default RecruiterPage;
