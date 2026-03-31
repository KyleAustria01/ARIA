import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faMicrophone,
  faBrain,
  faChartBar,
  faFileLines,
  faUser,
  faMagnifyingGlass,
  faLink,
  faHeadset,
  faChevronDown,
  faChevronUp,
  faArrowUp,
  faPrint,
  faRobot,
  faEarListen,
  faVolumeHigh,
  faGlobe,
  faShieldHalved,
  faCircleQuestion,
  faUserTie,
  faUserGroup,
  faBolt,
} from "@fortawesome/free-solid-svg-icons";
import Navbar from "../components/Navbar";
import styles from "./DocsPage.module.css";

/* ================================================================
   Section metadata — drives sidebar, scroll-spy, and search
   ================================================================ */

interface Section {
  id: string;
  label: string;
  icon: typeof faMicrophone;
}

const SECTIONS: Section[] = [
  { id: "what-is-aria",   label: "What is ARIA?",       icon: faRobot },
  { id: "how-it-works",   label: "How It Works",        icon: faBolt },
  { id: "for-recruiters",  label: "For Recruiters",      icon: faUserTie },
  { id: "for-candidates",  label: "For Candidates",      icon: faUserGroup },
  { id: "ai-behind-aria",  label: "The AI Behind ARIA",  icon: faBrain },
  { id: "privacy",         label: "Privacy & Data",      icon: faShieldHalved },
  { id: "faq",             label: "FAQ",                 icon: faCircleQuestion },
];

/* ================================================================
   FAQ data
   ================================================================ */

interface FaqItem {
  q: string;
  a: string;
}

const FAQ_DATA: FaqItem[] = [
  {
    q: "Does the candidate need to create an account?",
    a: "No. Candidates just open the link and start the interview. No signup, no password, no app to download.",
  },
  {
    q: "What happens if the AI makes a mistake?",
    a: "ARIA is an assistant, not the final decision maker. All results should be reviewed by a human recruiter before making hiring decisions.",
  },
  {
    q: "How long does the interview take?",
    a: "Typically 10\u201315 minutes depending on the role and the candidate\u2019s answers. ARIA decides when enough information has been collected.",
  },
  {
    q: "Can the candidate redo the interview?",
    a: "The interview link can only be used once. Contact the recruiter for a new link if needed.",
  },
  {
    q: "What languages does ARIA support?",
    a: "Currently English only. More languages coming soon.",
  },
  {
    q: "Is the interview recorded?",
    a: "Audio is processed in real time but not permanently stored. Only the text transcript is saved.",
  },
  {
    q: "Can I use ARIA on my phone?",
    a: "ARIA works best on desktop with Chrome or Firefox. Mobile support is limited.",
  },
  {
    q: "How accurate is the AI evaluation?",
    a: "ARIA provides a data-driven first assessment. It is designed to save recruiter time, not replace human judgment. Always review the full transcript alongside the verdict.",
  },
  {
    q: "What if the internet goes down during the interview?",
    a: "ARIA has offline fallbacks for most features. The interview may slow down but should continue.",
  },
  {
    q: "Is this GDPR compliant?",
    a: "Since no data is permanently stored and sessions expire in 24 hours, ARIA is designed with privacy in mind. Consult your legal team for full GDPR compliance requirements.",
  },
];

/* ================================================================
   Accordion component
   ================================================================ */

const FaqAccordion: React.FC<{ item: FaqItem; open: boolean; onToggle: () => void }> = ({
  item,
  open,
  onToggle,
}) => (
  <div className={`${styles.faqItem} ${open ? styles.faqItemOpen : ""}`}>
    <button type="button" className={styles.faqQuestion} onClick={onToggle}>
      <span>{item.q}</span>
      <FontAwesomeIcon icon={open ? faChevronUp : faChevronDown} className={styles.faqChevron} />
    </button>
    <div className={`${styles.faqAnswer} ${open ? styles.faqAnswerOpen : ""}`}>
      <p>{item.a}</p>
    </div>
  </div>
);

/* ================================================================
   DocsPage
   ================================================================ */

const DocsPage: React.FC = () => {
  const [activeId, setActiveId] = useState(SECTIONS[0].id);
  const [search, setSearch] = useState("");
  const [openFaq, setOpenFaq] = useState<number | null>(null);
  const [showTop, setShowTop] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);

  /* ── Scroll-spy ─────────────────────────────────────── */
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveId(entry.target.id);
          }
        }
      },
      { rootMargin: "-20% 0px -60% 0px", threshold: 0 },
    );

    for (const s of SECTIONS) {
      const el = document.getElementById(s.id);
      if (el) observer.observe(el);
    }

    return () => observer.disconnect();
  }, []);

  /* ── Show/hide back-to-top ──────────────────────────── */
  useEffect(() => {
    const onScroll = () => setShowTop(window.scrollY > 400);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  /* ── Sidebar search filter ──────────────────────────── */
  const filteredSections = useMemo(
    () =>
      search.trim()
        ? SECTIONS.filter((s) => s.label.toLowerCase().includes(search.toLowerCase()))
        : SECTIONS,
    [search],
  );

  /* ── Sidebar click ──────────────────────────────────── */
  const scrollTo = useCallback((id: string) => {
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
      setActiveId(id);
    }
  }, []);

  const handlePrint = useCallback(() => window.print(), []);

  return (
    <div className={styles.root}>
      <Navbar />

      <div className={styles.layout}>
        {/* ═══════════ SIDEBAR ═══════════ */}
        <aside className={styles.sidebar}>
          <div className={styles.sidebarInner}>
            {/* Search */}
            <div className={styles.searchWrap}>
              <FontAwesomeIcon icon={faMagnifyingGlass} className={styles.searchIcon} />
              <input
                type="text"
                className={styles.searchInput}
                placeholder="Search docs\u2026"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>

            {/* Nav links */}
            <nav className={styles.sidebarNav}>
              {filteredSections.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  className={`${styles.sidebarLink} ${activeId === s.id ? styles.sidebarLinkActive : ""}`}
                  onClick={() => scrollTo(s.id)}
                >
                  <FontAwesomeIcon icon={s.icon} className={styles.sidebarLinkIcon} />
                  {s.label}
                </button>
              ))}
            </nav>
          </div>
        </aside>

        {/* ═══════════ CONTENT ═══════════ */}
        <main className={styles.content} ref={contentRef}>
          {/* Print button */}
          <button type="button" className={styles.printBtn} onClick={handlePrint} aria-label="Print">
            <FontAwesomeIcon icon={faPrint} />
          </button>

          {/* ────────────────────────────────────────────
              SECTION 1: What is ARIA?
              ──────────────────────────────────────────── */}
          <section id="what-is-aria" className={styles.section}>
            <h1 className={styles.h1}>Meet ARIA &mdash; Your AI Interview Assistant</h1>
            <p className={styles.lead}>
              ARIA (Artificial Reasoning Interview Agent) is an AI-powered pre-screening system
              that conducts voice interviews with job candidates on your behalf.
            </p>
            <p>
              Instead of spending hours on initial phone screens, simply upload the job description
              and the candidate&apos;s resume. ARIA does the rest &mdash; analyzing both documents,
              researching the role, and conducting a personalized voice interview with your candidate.
            </p>
            <p>
              After the interview, you get a full transcript and a detailed AI evaluation with
              a hiring recommendation.
            </p>

            {/* Feature cards */}
            <div className={styles.featureGrid}>
              <div className={styles.featureCard}>
                <span className={styles.featureEmoji}><FontAwesomeIcon icon={faMicrophone} /></span>
                <h3>Voice Interview</h3>
                <p>Real conversation, not forms. Candidates speak naturally and ARIA listens.</p>
              </div>
              <div className={styles.featureCard}>
                <span className={styles.featureEmoji}><FontAwesomeIcon icon={faBrain} /></span>
                <h3>AI Analysis</h3>
                <p>Evaluates answers against the job description with intelligent follow-ups.</p>
              </div>
              <div className={styles.featureCard}>
                <span className={styles.featureEmoji}><FontAwesomeIcon icon={faChartBar} /></span>
                <h3>Instant Results</h3>
                <p>Full transcript, skill scores, and a hire/no-hire verdict in minutes.</p>
              </div>
            </div>
          </section>

          <hr className={styles.divider} />

          {/* ────────────────────────────────────────────
              SECTION 2: How It Works
              ──────────────────────────────────────────── */}
          <section id="how-it-works" className={styles.section}>
            <h1 className={styles.h1}>From Upload to Results in Minutes</h1>

            <div className={styles.stepFlow}>
              <Step num={1} icon={faFileLines} title="Upload the Job Description">
                Upload the JD as a PDF. ARIA reads and understands the role requirements, required
                skills, experience level, and responsibilities. No manual setup needed.
              </Step>
              <Step num={2} icon={faUser} title="Upload the Candidate&rsquo;s Resume">
                Upload the candidate&apos;s resume as a PDF. ARIA analyzes their experience, skills,
                and automatically calculates how well they match the job requirements.
              </Step>
              <Step num={3} icon={faMagnifyingGlass} title="ARIA Researches the Role">
                Before the interview begins, ARIA searches the internet for the latest industry
                standards, common interview questions, and benchmarks for the role. This ensures
                questions are relevant and current.
              </Step>
              <Step num={4} icon={faLink} title="Generate an Interview Link">
                Click one button to get a unique interview link. Share this link with your candidate
                via email, WhatsApp, or any messaging app. No account needed for the candidate.
              </Step>
              <Step num={5} icon={faHeadset} title="Candidate Completes the Interview">
                The candidate opens the link, enables their microphone, and speaks their answers
                naturally. ARIA listens, understands, and asks follow-up questions &mdash; just like
                a real interviewer.
              </Step>
              <Step num={6} icon={faChartBar} title="Review the Results" last>
                Once the interview is complete, you get a full interview transcript, a score for each
                skill area, an AI hiring recommendation, plus strengths and areas of concern.
              </Step>
            </div>
          </section>

          <hr className={styles.divider} />

          {/* ────────────────────────────────────────────
              SECTION 3: For Recruiters
              ──────────────────────────────────────────── */}
          <section id="for-recruiters" className={styles.section}>
            <h1 className={styles.h1}>A Simple Guide for Recruiters</h1>

            <h2 className={styles.h2}>Uploading a Job Description</h2>
            <p>
              Upload any PDF job description. After uploading, ARIA will show you what it extracted:
            </p>
            <ul className={styles.checkList}>
              <li>Job title</li>
              <li>Required skills</li>
              <li>Years of experience needed</li>
              <li>Key responsibilities</li>
            </ul>
            <p>Review the extracted info to make sure it looks correct before proceeding.</p>

            <h2 className={styles.h2}>Uploading a Resume</h2>
            <p>Upload the candidate&apos;s resume as PDF. ARIA will show you:</p>
            <ul className={styles.checkList}>
              <li>Candidate name (auto-detected)</li>
              <li>Their current role and experience</li>
              <li>Skills they have</li>
              <li>Match score vs the JD (e.g. 85%)</li>
              <li>Skills they are missing</li>
            </ul>
            <div className={styles.callout}>
              The match score helps you quickly decide if the candidate is worth interviewing.
            </div>

            <h2 className={styles.h2}>Generating the Interview Link</h2>
            <p>
              Once both PDFs are uploaded, click <strong>&ldquo;Generate Interview Link&rdquo;</strong>.
              You will get a unique URL like:
            </p>
            <div className={styles.codeBlock}>aria.yourdomain.com/interview/abc123</div>
            <p>Share this link with your candidate. The link is valid for 24 hours.</p>

            <h2 className={styles.h2}>Viewing Results</h2>
            <p>After the interview, visit:</p>
            <div className={styles.codeBlock}>aria.yourdomain.com/results/abc123</div>
            <p>
              to see the full report. No login needed &mdash; just save the results URL when you
              generate the link.
            </p>
          </section>

          <hr className={styles.divider} />

          {/* ────────────────────────────────────────────
              SECTION 4: For Candidates
              ──────────────────────────────────────────── */}
          <section id="for-candidates" className={styles.section}>
            <h1 className={styles.h1}>What to Expect as a Candidate</h1>

            <h2 className={styles.h2}>Before You Start</h2>
            <p>Make sure you have:</p>
            <ul className={styles.checkList}>
              <li>A working microphone</li>
              <li>A quiet environment</li>
              <li>Google Chrome or Firefox browser</li>
              <li>The interview link from the recruiter</li>
            </ul>

            <h2 className={styles.h2}>Joining the Interview</h2>
            <ol className={styles.orderedList}>
              <li>Open the link on your computer</li>
              <li>Allow microphone access when prompted</li>
              <li>Optionally enable your camera</li>
              <li>Enter your name if asked</li>
              <li>Click &ldquo;Join Interview&rdquo;</li>
            </ol>

            <h2 className={styles.h2}>During the Interview</h2>
            <ul className={styles.bulletList}>
              <li>ARIA will introduce itself and explain the process</li>
              <li>ARIA asks one question at a time</li>
              <li>Wait for ARIA to finish speaking, then click the microphone button</li>
              <li>Speak your answer clearly and naturally</li>
              <li>Click stop when you are done</li>
              <li>ARIA will process your answer and ask the next question</li>
            </ul>

            <h2 className={styles.h2}>Tips for a Good Interview</h2>
            <div className={styles.tipGrid}>
              <div className={styles.tipCard}>Speak clearly and at a normal pace</div>
              <div className={styles.tipCard}>Give specific examples from your experience</div>
              <div className={styles.tipCard}>It&apos;s okay to take a moment to think</div>
              <div className={styles.tipCard}>The interview takes 10&ndash;15 minutes</div>
              <div className={styles.tipCard}>There are no trick questions</div>
            </div>

            <h2 className={styles.h2}>After the Interview</h2>
            <p>
              Once complete you will see a summary screen. The recruiter will review your full
              results separately.
            </p>
          </section>

          <hr className={styles.divider} />

          {/* ────────────────────────────────────────────
              SECTION 5: The AI Behind ARIA
              ──────────────────────────────────────────── */}
          <section id="ai-behind-aria" className={styles.section}>
            <h1 className={styles.h1}>The Technology Powering ARIA</h1>
            <p>
              ARIA uses multiple AI systems working together. Here is what each one does in plain
              language:
            </p>

            {/* Language AI */}
            <div className={styles.aiCard}>
              <div className={styles.aiCardHeader}>
                <FontAwesomeIcon icon={faBrain} className={styles.aiCardIcon} />
                <h3>Language AI (The Brain)</h3>
              </div>
              <p>
                ARIA uses large language models to understand your answers and generate intelligent
                follow-up questions. ARIA tries multiple AI providers in order from fastest to slowest:
              </p>
              <div className={styles.providerTable}>
                <div className={styles.providerRow}>
                  <span className={styles.providerRank}>1st</span>
                  <div className={styles.providerInfo}>
                    <strong>Cerebras AI</strong>
                    <span className={styles.providerUse}>Generating questions, evaluating answers</span>
                  </div>
                  <div className={styles.speedBar}><div className={styles.speedFill} style={{ width: "100%" }} /></div>
                  <span className={styles.badge}>Primary</span>
                </div>
                <div className={styles.providerRow}>
                  <span className={styles.providerRank}>2nd</span>
                  <div className={styles.providerInfo}>
                    <strong>Groq</strong>
                    <span className={styles.providerUse}>Backup when Cerebras is unavailable</span>
                  </div>
                  <div className={styles.speedBar}><div className={styles.speedFill} style={{ width: "80%" }} /></div>
                  <span className={`${styles.badge} ${styles.badgeFallback}`}>Fallback</span>
                </div>
                <div className={styles.providerRow}>
                  <span className={styles.providerRank}>3rd</span>
                  <div className={styles.providerInfo}>
                    <strong>Google Gemini</strong>
                    <span className={styles.providerUse}>Additional fallback</span>
                  </div>
                  <div className={styles.speedBar}><div className={styles.speedFill} style={{ width: "60%" }} /></div>
                  <span className={`${styles.badge} ${styles.badgeFallback}`}>Fallback</span>
                </div>
                <div className={styles.providerRow}>
                  <span className={styles.providerRank}>4th</span>
                  <div className={styles.providerInfo}>
                    <strong>Local AI (Ollama / LLaMA)</strong>
                    <span className={styles.providerUse}>Offline fallback when no internet AI is available</span>
                  </div>
                  <div className={styles.speedBar}><div className={styles.speedFill} style={{ width: "30%" }} /></div>
                  <span className={`${styles.badge} ${styles.badgeOffline}`}>Offline</span>
                </div>
              </div>
              <div className={styles.callout}>
                This fallback system means ARIA keeps working even if one AI provider is temporarily unavailable.
              </div>
            </div>

            {/* Speech to Text */}
            <div className={styles.aiCard}>
              <div className={styles.aiCardHeader}>
                <FontAwesomeIcon icon={faEarListen} className={styles.aiCardIcon} />
                <h3>Speech to Text (Listening)</h3>
              </div>
              <p>When you speak your answer, ARIA converts your voice to text using:</p>
              <ul className={styles.bulletList}>
                <li><strong>1st Choice: Groq Whisper</strong> &mdash; extremely fast and accurate voice transcription</li>
                <li><strong>2nd Choice: Local Whisper</strong> &mdash; runs on your computer, works offline</li>
              </ul>
            </div>

            {/* Text to Speech */}
            <div className={styles.aiCard}>
              <div className={styles.aiCardHeader}>
                <FontAwesomeIcon icon={faVolumeHigh} className={styles.aiCardIcon} />
                <h3>Text to Speech (Speaking)</h3>
              </div>
              <p>
                ARIA speaks questions using an offline voice engine that works without internet.
              </p>
            </div>

            {/* Web Research */}
            <div className={styles.aiCard}>
              <div className={styles.aiCardHeader}>
                <FontAwesomeIcon icon={faGlobe} className={styles.aiCardIcon} />
                <h3>Web Research</h3>
              </div>
              <p>
                Before each interview, ARIA automatically searches the internet using Tavily Search
                to find the latest interview questions and industry benchmarks for the role. This
                ensures questions are always relevant and up to date.
              </p>
            </div>
          </section>

          <hr className={styles.divider} />

          {/* ────────────────────────────────────────────
              SECTION 6: Privacy & Data
              ──────────────────────────────────────────── */}
          <section id="privacy" className={styles.section}>
            <h1 className={styles.h1}>Your Data is Safe</h1>

            <h2 className={styles.h2}>What We Store</h2>
            <p>During an interview session, ARIA temporarily stores:</p>
            <ul className={styles.bulletList}>
              <li>The job description text</li>
              <li>The resume text</li>
              <li>The interview transcript</li>
              <li>The AI evaluation results</li>
            </ul>

            <h2 className={styles.h2}>How Long We Keep It</h2>
            <p>
              All data is automatically deleted after 24 hours. There is no permanent database.
              Everything is stored in temporary memory only.
            </p>

            <h2 className={styles.h2}>No Account Required</h2>
            <p>
              Candidates do not create accounts. Recruiters do not need to log in.
              No personal data is permanently saved.
            </p>
          </section>

          <hr className={styles.divider} />

          {/* ────────────────────────────────────────────
              SECTION 7: FAQ
              ──────────────────────────────────────────── */}
          <section id="faq" className={styles.section}>
            <h1 className={styles.h1}>Frequently Asked Questions</h1>

            <div className={styles.faqList}>
              {FAQ_DATA.map((item, i) => (
                <FaqAccordion
                  key={i}
                  item={item}
                  open={openFaq === i}
                  onToggle={() => setOpenFaq(openFaq === i ? null : i)}
                />
              ))}
            </div>
          </section>

          {/* Bottom spacer */}
          <div style={{ height: 80 }} />
        </main>
      </div>

      {/* Back-to-top */}
      {showTop && (
        <button
          type="button"
          className={styles.backToTop}
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
          aria-label="Back to top"
        >
          <FontAwesomeIcon icon={faArrowUp} />
        </button>
      )}
    </div>
  );
};

/* ================================================================
   Step sub-component for the "How It Works" flow
   ================================================================ */

const Step: React.FC<{
  num: number;
  icon: typeof faMicrophone;
  title: string;
  children: React.ReactNode;
  last?: boolean;
}> = ({ num, icon, title, children, last }) => (
  <div className={`${styles.step} ${last ? styles.stepLast : ""}`}>
    <div className={styles.stepTimeline}>
      <div className={styles.stepCircle}>{num}</div>
      {!last && <div className={styles.stepLine} />}
    </div>
    <div className={styles.stepBody}>
      <div className={styles.stepIcon}>
        <FontAwesomeIcon icon={icon} />
      </div>
      <h3 className={styles.stepTitle}>{title}</h3>
      <p className={styles.stepDesc}>{children}</p>
    </div>
  </div>
);

export default DocsPage;
