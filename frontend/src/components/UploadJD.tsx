import React, { useState } from "react";
import { useAuth } from "../context/AuthContext";

const UploadJD: React.FC = () => {
  const { token } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [filePath, setFilePath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFile(e.target.files?.[0] || null);
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch("/api/recruiter/upload-jd", {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      });
      if (!res.ok) throw new Error("Upload failed");
      const data = await res.json();
      setFilePath(data.file_path);
    } catch (err: any) {
      setError(err.message || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <form onSubmit={handleUpload}>
      <h2>Upload Job Description PDF</h2>
      <input type="file" accept="application/pdf" onChange={handleFileChange} required />
      <button type="submit" disabled={uploading || !file}>
        {uploading ? "Uploading..." : "Upload"}
      </button>
      {filePath && <div>Uploaded: {filePath}</div>}
      {error && <div style={{ color: "red" }}>{error}</div>}
    </form>
  );
};

export default UploadJD;
