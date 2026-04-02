"""
Test script for ARIA interview flow — type instead of speak.

Usage:
    python test_interview.py

This script:
1. Parses the JD PDF
2. Uses a mock resume (or provide your own)
3. Generates skill rules
4. Runs an interactive text-based interview
"""

import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.utils.pdf_parser import parse_jd, parse_resume, generate_skill_rules
from backend.interview.engine import InterviewEngine
from backend.interview.state import InterviewState


# ─────────────────────────────────────────────────────────────────
# Mock resume data (edit this or use actual PDF)
# ─────────────────────────────────────────────────────────────────

MOCK_RESUME = {
    "candidate_name": "Kyle Austria",
    "email": "kyle@example.com",
    "phone": "+63 912 345 6789",
    "current_role": "Full Stack Developer",
    "total_experience_years": 3,
    "skills": [
        "PHP", "Laravel", "MySQL", "PostgreSQL", "Redis",
        "Angular", "TypeScript", "JavaScript", "HTML", "CSS",
        "AWS", "Docker", "Git", "REST API", "Eloquent ORM",
        "Vue.js", "Node.js", "Python", "Agile", "CI/CD"
    ],
    "experience": [
        {
            "company": "Clark Outsourcing",
            "role": "Full Stack Developer",
            "duration": "2022 - Present",
            "highlights": [
                "Built internal enterprise systems: payroll, employee management, performance tracking",
                "Used Laravel for API development, business logic, database interaction via Eloquent",
                "Implemented background jobs through Laravel Queues",
                "Angular frontend with AWS infrastructure"
            ]
        },
        {
            "company": "Previous Company",
            "role": "Junior Developer",
            "duration": "2020 - 2022",
            "highlights": [
                "Learned PHP and Laravel during internship",
                "Worked on small internal tools and CRUD applications"
            ]
        }
    ],
    "education": [
        {
            "institution": "University of the Philippines",
            "degree": "BS Computer Science",
            "year": "2020"
        }
    ],
    "raw_text": """
    Kyle Austria
    Full Stack Developer | PHP Laravel | Angular | AWS
    3 years experience building enterprise applications
    Currently at Clark Outsourcing building payroll and HR systems.
    Skills: PHP, Laravel, MySQL, Angular, TypeScript, AWS, Docker, Git
    """
}


async def main():
    print("\n" + "=" * 60)
    print("  ARIA Interview Test (Text Mode)")
    print("=" * 60)

    # ── Step 1: Parse JD ──────────────────────────────────────────
    jd_path = r"c:\Users\Austria\Downloads\b7zOkPMsqDdPrXNLEGmBDuhEbMzWHdfAqLJiCknG.pdf"
    
    print("\n[1/4] Parsing JD...")
    jd_data = await parse_jd(jd_path)
    print(f"  Job Title: {jd_data.get('job_title', 'N/A')}")
    print(f"  Company: {jd_data.get('company', 'N/A')}")
    print(f"  Required Skills ({len(jd_data.get('required_skills', []))}): {', '.join(jd_data.get('required_skills', [])[:8])}")

    # ── Step 2: Use mock resume ───────────────────────────────────
    print("\n[2/4] Using mock resume...")
    resume_data = MOCK_RESUME
    
    # Compute match (simplified)
    required = set(s.lower() for s in jd_data.get("required_skills", []))
    candidate = set(s.lower() for s in resume_data.get("skills", []))
    matched = required & candidate
    missing = required - candidate
    match_score = int(len(matched) / len(required) * 100) if required else 0
    
    resume_data["match_score"] = match_score
    resume_data["matched_skills"] = list(matched)
    resume_data["missing_skills"] = list(missing)
    
    print(f"  Candidate: {resume_data['candidate_name']}")
    print(f"  Match Score: {match_score}%")
    print(f"  Matched: {', '.join(list(matched)[:6])}")

    # ── Step 3: Generate skill rules ──────────────────────────────
    print("\n[3/4] Generating skill rules (LLM call)...")
    skill_rules = await generate_skill_rules(jd_data, resume_data)
    print(f"  Generated {len(skill_rules)} skill rules:")
    for rule in skill_rules[:5]:
        print(f"    - {rule['skill']}: {rule['angle']}")
    
    # ── Step 4: Build interview state ─────────────────────────────
    print("\n[4/4] Building interview state...")
    state = InterviewState(
        session_id="test-session",
        job_title=jd_data.get("job_title", "Senior PHP Laravel"),
        company=jd_data.get("company", "Clark Outsourcing"),
        required_skills=jd_data.get("required_skills", []),
        nice_to_have_skills=jd_data.get("nice_to_have_skills", []),
        responsibilities=jd_data.get("responsibilities", []),
        candidate_name=resume_data["candidate_name"],
        current_role=resume_data["current_role"],
        total_experience_years=resume_data["total_experience_years"],
        candidate_skills=resume_data["skills"],
        match_score=match_score,
        matched_skills=list(matched),
        missing_skills=list(missing),
        skill_rules=skill_rules,
        max_questions=8,
    )
    
    engine = InterviewEngine(state)
    engine.build_interview_context()

    # ── Interactive Interview ─────────────────────────────────────
    print("\n" + "=" * 60)
    print("  INTERVIEW STARTED — Type your answers")
    print("  (Type 'quit' to exit, 'debug' to see state)")
    print("=" * 60)

    # Greeting
    print("\n[ARIA generating greeting...]")
    greeting = await engine.generate_greeting()
    print(f"\n🔵 ARIA: {greeting}\n")

    turn = 0
    while not engine.state.is_complete:
        turn += 1
        
        # Get candidate input
        print("-" * 40)
        candidate_input = input(f"👤 You (Turn {turn}): ").strip()
        
        if candidate_input.lower() == "quit":
            print("\n[Interview ended by user]")
            break
        
        if candidate_input.lower() == "debug":
            print(f"\n[DEBUG]")
            print(f"  Question count: {engine.state.question_count}/{engine.state.max_questions}")
            print(f"  Current skill idx: {engine._current_skill_idx}")
            print(f"  Current skill: {engine._current_skill()}")
            entry = engine._current_skill_entry()
            if entry:
                print(f"  Current angle: {entry.get('angle', 'N/A')}")
                print(f"  Sample Q: {entry.get('sample_question', 'N/A')[:80]}...")
            print(f"  Covered: {engine.state.covered_skill_areas}")
            print(f"  Scores: {len(engine.state.scores)}")
            continue
        
        if not candidate_input:
            candidate_input = "I'm not sure, can we move on?"
        
        # Process turn
        print("\n[ARIA thinking...]")
        result = await engine.process_turn(candidate_input)
        
        # Show score entry
        se = result.score_entry
        if se.get("score", 0) > 0:
            print(f"  [Score: {se.get('score')}/10 | Skill: {se.get('skill_area')} | Action: {se.get('action')}]")
        
        print(f"\n🔵 ARIA: {result.aria_text}\n")
        
        if result.should_end:
            print("\n[Interview complete — generating verdict...]")
            
            # Skip logistics for test
            engine.state.logistics_raw = [
                {"question": "Availability?", "answer": "I can start in 2 weeks"},
                {"question": "Salary?", "answer": "I'm flexible, around 50-60k"},
            ]
            
            verdict = await engine.generate_verdict()
            print("\n" + "=" * 60)
            print("  VERDICT")
            print("=" * 60)
            print(f"  Overall: {verdict.get('overall_verdict', 'N/A')}")
            print(f"  Score: {verdict.get('overall_score', 0)}/10")
            print(f"  Recommendation: {verdict.get('recommendation', 'N/A')}")
            print(f"  Strengths: {verdict.get('strengths', [])}")
            print(f"  Concerns: {verdict.get('concerns', [])}")
            break

    print("\n[Test complete]")


if __name__ == "__main__":
    asyncio.run(main())
