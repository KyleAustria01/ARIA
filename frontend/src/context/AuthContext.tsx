import React, { createContext, useContext, useState, ReactNode } from "react";

interface AuthContextType {
  token: string | null;
  setToken: (token: string | null) => void;
  role: "recruiter" | "applicant" | null;
  setRole: (role: "recruiter" | "applicant" | null) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [token, setTokenState] = useState<string | null>(() => sessionStorage.getItem("token"));
  const [role, setRoleState] = useState<"recruiter" | "applicant" | null>(() => sessionStorage.getItem("role") as "recruiter" | "applicant" | null);

  const setToken = (token: string | null) => {
    setTokenState(token);
    if (token) sessionStorage.setItem("token", token);
    else sessionStorage.removeItem("token");
  };

  const setRole = (role: "recruiter" | "applicant" | null) => {
    setRoleState(role);
    if (role) sessionStorage.setItem("role", role);
    else sessionStorage.removeItem("role");
  };

  return (
    <AuthContext.Provider value={{ token, setToken, role, setRole }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};
