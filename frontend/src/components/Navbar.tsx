import React from "react";
import { Link, useLocation } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faSun,
  faMoon,
  faUser,
} from "@fortawesome/free-solid-svg-icons";
import { useTheme } from "../hooks/useTheme";
import styles from "./Navbar.module.css";

interface NavItem {
  to: string;
  label: string;
}

const NAV_LINKS: NavItem[] = [
  { to: "/", label: "Recruiter" },
  { to: "/docs", label: "Docs" },
];

const Navbar: React.FC = () => {
  const { theme, toggle: toggleTheme } = useTheme();
  const location = useLocation();

  const isActive = (path: string) =>
    path === "/" ? location.pathname === "/" : location.pathname.startsWith(path);

  return (
    <nav className={styles.navbar}>
      {/* Left — Logo */}
      <div className={styles.left}>
        <Link to="/" className={styles.logoLink}>
          <span className={styles.logoDots}>
            <span className={styles.dotIndigo} />
            <span className={styles.dotPurple} />
          </span>
          <span className={styles.logoText}>ARIA</span>
        </Link>

        {/* Nav links */}
        <div className={styles.navLinks}>
          {NAV_LINKS.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              className={`${styles.navLink} ${isActive(link.to) ? styles.navLinkActive : ""}`}
            >
              {link.label}
            </Link>
          ))}
        </div>
      </div>

      {/* Right — Theme toggle + avatar */}
      <div className={styles.right}>
        <button
          type="button"
          className={styles.iconBtn}
          onClick={toggleTheme}
          aria-label="Toggle theme"
        >
          <FontAwesomeIcon icon={theme === "dark" ? faSun : faMoon} />
        </button>

        <button type="button" className={styles.avatar} aria-label="Account">
          <FontAwesomeIcon icon={faUser} />
        </button>
      </div>
    </nav>
  );
};

export default Navbar;
