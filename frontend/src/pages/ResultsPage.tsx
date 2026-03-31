import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArrowLeft,
  faCircleCheck,
  faCircleXmark,
  faLightbulb,
  faShieldHalved,
  faTriangleExclamation,
  faClipboardList,
  faChartSimple,
} from "@fortawesome/free-solid-svg-icons";
import Navbar from "../components/Navbar";
import styles from "./ResultsPage.module.css";

interface ScoreEntry {
  question: string;
  answer: string;
  score: number;
  feedback: string;
  skill_area: string;
}

interface Verdict {
  overall_verdict: string;
  overall_score: number;
  strengths: string[];
  concerns: string[];
  recommendation: string;
  skill_scores?: Record<string, number>;
  questions_asked?: number;
  avg_score?: number;
}

interface SessionData {
  candidate_name: string;
  job_title: string;
  company: string;
  scores: ScoreEntry[];
  verdict: Verdict;
  is_complete: boolean;
}

const VERDICT_COLOR: Record<string, string> = {
  "Strong Hire": "var(--success)",
  Hire: "#6ee7b7",
  Maybe: "#fbbf24",
  "No Hire": "var(--error)",
};

const ResultsPage: React.FC = () => {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [data, setData] = useState<SessionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!sessionId) { setError("No session ID"); setLoading(false); return; }
    fetch(`/api/recruiter/session/${sessionId}`)
      .then((r) => {
        if (!r.ok) throw new Error(`Session not found (${r.status})`);
        return r.json();
      })
      .then((d: SessionData) => { setData(d); setLoading(false); })
      .catch((err: Error) => { setError(err.message); setLoading(false); });
  }, [sessionId]);

  if (loading) {
    return (
      <div className={styles.center}>
        <div className={styles.spinner} />
        <span>Loading results…</span>
      </div>
    );
  }
  if (error || !data) return <div className={styles.center}><p className={styles.error}>{error ?? "No data"}</p></div>;
  if (!data.is_complete) return (
    <div className={styles.center}>
      <p className={styles.sub}>Interview not yet complete.</p>
      <Link to={`/interview/${sessionId}`} className={styles.backLink}>
        <FontAwesomeIcon icon={faArrowLeft} /> Go to Interview
      </Link>
    </div>
  );

  const verdict = data.verdict ?? {};
  const verdictLabel = verdict.overall_verdict ?? "—";
  const verdictColor = VERDICT_COLOR[verdictLabel] ?? "var(--text-muted)";
  const scoreColor = (s: number) => s >= 7 ? "var(--success)" : s >= 4 ? "#fbbf24" : "var(--error)";

  return (
    <div className="app-container">
      <Navbar />

      <main className={styles.main}>
        {/* Page Header */}
        <div className={styles.pageHeader}>
          <Link to="/" className={styles.backBtn}>
            <FontAwesomeIcon icon={faArrowLeft} />
          </Link>
          <div>
            <h1 className={styles.pageTitle}>Interview Results</h1>
            <p className={styles.pageSub}>Session {sessionId?.slice(0, 8)}</p>
          </div>
        </div>

        {/* Hero Card */}
        <div className={styles.hero}>
          <div className={styles.heroLeft}>
            <div className={styles.heroAvatar}>
              {data.candidate_name.charAt(0).toUpperCase()}
            </div>
            <div>
              <p className={styles.heroName}>{data.candidate_name}</p>
              <p className={styles.heroRole}>
                {data.job_title}{data.company ? ` · ${data.company}` : ""}
              </p>
            </div>
          </div>
          <div className={styles.heroRight}>
            <span
              className={styles.verdictBadge}
              style={{ color: verdictColor, borderColor: verdictColor }}
            >
              {verdictLabel}
            </span>
            {verdict.overall_score != null && (
              <span className={styles.overallScore}>
                {verdict.overall_score.toFixed(1)}
                <span className={styles.scoreMax}>/10</span>
              </span>
            )}
          </div>
        </div>

        {/* Recommendation */}
        {verdict.recommendation && (
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <FontAwesomeIcon icon={faLightbulb} className={styles.cardIcon} />
              <h2 className={styles.cardTitle}>Recommendation</h2>
            </div>
            <p className={styles.recommendation}>{verdict.recommendation}</p>
          </div>
        )}

        {/* Strengths & Concerns */}
        <div className={styles.twoCol}>
          {verdict.strengths?.length > 0 && (
            <div className={styles.card}>
              <div className={styles.cardHeader}>
                <FontAwesomeIcon icon={faShieldHalved} className={styles.cardIconGreen} />
                <h2 className={styles.cardTitle}>Strengths</h2>
              </div>
              <ul className={styles.list}>
                {verdict.strengths.map((s, i) => (
                  <li key={i} className={styles.strength}>
                    <FontAwesomeIcon icon={faCircleCheck} className={styles.listIcon} />
                    {s}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {verdict.concerns?.length > 0 && (
            <div className={styles.card}>
              <div className={styles.cardHeader}>
                <FontAwesomeIcon icon={faTriangleExclamation} className={styles.cardIconAmber} />
                <h2 className={styles.cardTitle}>Concerns</h2>
              </div>
              <ul className={styles.list}>
                {verdict.concerns.map((c, i) => (
                  <li key={i} className={styles.concern}>
                    <FontAwesomeIcon icon={faCircleXmark} className={styles.listIcon} />
                    {c}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Per-question scores */}
        {data.scores?.length > 0 && (
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <FontAwesomeIcon icon={faClipboardList} className={styles.cardIcon} />
              <h2 className={styles.cardTitle}>Question Breakdown</h2>
              <span className={styles.cardCount}>{data.scores.length} questions</span>
            </div>
            <div className={styles.scoreList}>
              {data.scores.map((entry, i) => (
                <div key={i} className={styles.scoreItem}>
                  <div className={styles.scoreHeader}>
                    <span className={styles.qBadge}>Q{i + 1}</span>
                    <span className={styles.skillArea}>{entry.skill_area}</span>
                    <span className={styles.scoreBar}>
                      <span
                        className={styles.scoreFill}
                        style={{
                          width: `${entry.score * 10}%`,
                          background: scoreColor(entry.score),
                        }}
                      />
                    </span>
                    <span className={styles.scoreNum} style={{ color: scoreColor(entry.score) }}>
                      {entry.score}/10
                    </span>
                  </div>
                  <p className={styles.questionText}>{entry.question}</p>
                  <p className={styles.answerText}>"{entry.answer}"</p>
                  {entry.feedback && <p className={styles.feedback}>{entry.feedback}</p>}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Skill Scores */}
        {verdict.skill_scores && Object.keys(verdict.skill_scores).length > 0 && (
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <FontAwesomeIcon icon={faChartSimple} className={styles.cardIcon} />
              <h2 className={styles.cardTitle}>Skill Scores</h2>
            </div>
            <div className={styles.skillGrid}>
              {Object.entries(verdict.skill_scores).map(([skill, score]) => (
                <div key={skill} className={styles.skillItem}>
                  <span className={styles.skillName}>{skill}</span>
                  <span className={styles.scoreBar}>
                    <span
                      className={styles.scoreFill}
                      style={{
                        width: `${score * 10}%`,
                        background: scoreColor(score),
                      }}
                    />
                  </span>
                  <span className={styles.skillScore} style={{ color: scoreColor(score) }}>
                    {score.toFixed(1)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className={styles.footer}>
          <Link to="/" className={styles.footerBtn}>
            <FontAwesomeIcon icon={faArrowLeft} /> New Session
          </Link>
        </div>
      </main>
    </div>
  );
};

export default ResultsPage;
