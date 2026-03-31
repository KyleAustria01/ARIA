import React from "react";

interface VerdictProps {
  verdict: {
    overall_score: number;
    strengths: string;
    weaknesses: string;
    verdict: string;
  } | null;
}

const Verdict: React.FC<VerdictProps> = ({ verdict }) => {
  if (!verdict) return null;
  return (
    <div>
      <h2>Final Verdict</h2>
      <div>Overall Score: {verdict.overall_score}</div>
      <div>Strengths: {verdict.strengths}</div>
      <div>Weaknesses: {verdict.weaknesses}</div>
      <div>Verdict: <b>{verdict.verdict}</b></div>
    </div>
  );
};

export default Verdict;
