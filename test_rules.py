"""Quick test for skill rules generation."""
import asyncio
import sys
sys.path.insert(0, ".")

from backend.utils.pdf_parser import parse_jd, generate_skill_rules

MOCK_RESUME = {
    "candidate_name": "Kyle Austria",
    "current_role": "Full Stack Developer", 
    "total_experience_years": 3,
    "skills": ["PHP", "Laravel", "MySQL", "Angular", "AWS", "Docker", "Git", "REST API", "Eloquent ORM"],
    "experience": [
        {
            "company": "Clark Outsourcing",
            "role": "Full Stack Developer",
            "duration": "2022 - Present",
            "highlights": [
                "Built internal enterprise systems: payroll, employee management",
                "Used Laravel for API development, Eloquent ORM",
                "Angular frontend with AWS infrastructure"
            ]
        }
    ]
}

async def test():
    print("Parsing JD...")
    jd = await parse_jd(r"c:\Users\Austria\Downloads\b7zOkPMsqDdPrXNLEGmBDuhEbMzWHdfAqLJiCknG.pdf")
    print(f"Job: {jd.get('job_title')}")
    print(f"Skills: {jd.get('required_skills', [])[:8]}")
    
    print()
    print("Generating skill rules...")
    rules = await generate_skill_rules(jd, MOCK_RESUME)
    
    print()
    print("=" * 60)
    print("SKILL RULES GENERATED")
    print("=" * 60)
    for r in rules:
        print(f"SKILL: {r['skill']}")
        print(f"  ANGLE: {r['angle']}")
        ev = r.get("resume_evidence", "N/A")
        print(f"  EVIDENCE: {ev[:80]}..." if len(ev) > 80 else f"  EVIDENCE: {ev}")
        print(f"  SAMPLE Q: {r['sample_question']}")
        print()

asyncio.run(test())
