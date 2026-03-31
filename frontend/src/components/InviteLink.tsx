import React, { useState } from "react";
import { useAuth } from "../context/AuthContext";

const InviteLink: React.FC = () => {
  const { token } = useAuth();
  const [applicantName, setApplicantName] = useState("");
  const [role, setRole] = useState("");
  const [inviteToken, setInviteToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append("applicant_name", applicantName);
      formData.append("role", role);
      const res = await fetch("/api/recruiter/generate-invite", {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      });
      if (!res.ok) throw new Error("Failed to generate invite");
      const data = await res.json();
      setInviteToken(data.invite_token);
    } catch (err: any) {
      setError(err.message || "Failed to generate invite");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <h2>Generate Invite Link</h2>
      <input
        type="text"
        placeholder="Applicant Name"
        value={applicantName}
        onChange={e => setApplicantName(e.target.value)}
        required
      />
      <input
        type="text"
        placeholder="Role"
        value={role}
        onChange={e => setRole(e.target.value)}
        required
      />
      <button type="submit" disabled={loading}>
        {loading ? "Generating..." : "Generate Invite"}
      </button>
      {inviteToken && (
        <div>
          Invite Link: <code>http://localhost:5173/interview/{inviteToken}</code>
        </div>
      )}
      {error && <div style={{ color: "red" }}>{error}</div>}
    </form>
  );
};

export default InviteLink;
