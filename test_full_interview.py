"""
Full interview simulation with pre-defined answers.
Shows how ARIA progresses through skills with distinct questions.
"""
import asyncio
import sys
sys.path.insert(0, ".")

from backend.utils.pdf_parser import parse_jd, generate_skill_rules
from backend.interview.engine import InterviewEngine
from backend.interview.state import InterviewState

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

# Simulated candidate answers
CANDIDATE_ANSWERS = [
    # Intro
    "Hi, I'm Kyle, a full stack developer with three years experience. I've been at Clark Outsourcing since 2022, building internal enterprise systems like payroll and employee management using Laravel, Angular, and AWS.",
    
    # PHP-specific
    "I've been using PHP 8 features like match expressions for cleaner switch statements and typed properties. In our payroll calculations, I use strict typing to catch errors at compile time rather than runtime.",
    
    # Laravel service container
    "For our reporting module, I created a ReportGeneratorService that gets injected into controllers. I bound it to an interface so we can swap implementations for testing. Makes unit testing much easier.",
    
    # N+1 queries
    "In the employee listing API, I noticed it was making separate queries for each employee's department. I used Laravel Debugbar to spot it, then added eager loading with ->with('department', 'manager'). Cut queries from 200+ to just 3.",
    
    # Caching
    "For our dashboard stats, I cache the aggregated data in Redis with a 5-minute TTL. When an employee record updates, I use cache tags to invalidate related keys. Laravel's cache facade makes this pretty straightforward.",
    
    # Performance measurement
    "I use Laravel Telescope in staging and New Relic in production. Before and after optimization, I run the same query set and compare average response times. Usually aim for at least 50% improvement to justify the refactor.",
]

async def main():
    print("\n" + "=" * 70)
    print("  ARIA Interview Simulation — Senior PHP Laravel")
    print("=" * 70)
    
    # Parse JD
    print("\n[Parsing JD...]")
    jd = await parse_jd(r"c:\Users\Austria\Downloads\b7zOkPMsqDdPrXNLEGmBDuhEbMzWHdfAqLJiCknG.pdf")
    
    # Generate skill rules
    print("[Generating skill rules...]")
    rules = await generate_skill_rules(jd, MOCK_RESUME)
    print(f"[Generated {len(rules)} skill rules]")
    
    # Build state
    state = InterviewState(
        session_id="test",
        job_title=jd.get("job_title", "Senior PHP Laravel"),
        company=jd.get("company", "Clark Outsourcing"),
        required_skills=jd.get("required_skills", []),
        nice_to_have_skills=jd.get("nice_to_have_skills", []),
        candidate_name="Kyle Austria",
        candidate_address="Kyle",
        current_role="Full Stack Developer",
        total_experience_years=3,
        candidate_skills=MOCK_RESUME["skills"],
        skill_rules=rules,
        max_questions=6,  # Shorter for demo
    )
    
    engine = InterviewEngine(state)
    engine.build_interview_context()
    
    # Show skill queue
    print("\n" + "-" * 70)
    print("SKILL QUEUE (first 6):")
    for i, entry in enumerate(engine._skill_queue[:6]):
        print(f"  {i+1}. {entry['skill']} → {entry.get('angle', 'N/A')}")
    print("-" * 70)
    
    # Greeting
    print("\n[ARIA generating greeting...]")
    greeting = await engine.generate_greeting()
    print(f"\n🔵 ARIA: {greeting}")
    
    # Run through simulated answers
    for i, answer in enumerate(CANDIDATE_ANSWERS):
        if engine.state.is_complete:
            break
            
        print(f"\n{'='*70}")
        print(f"TURN {i+1}")
        print(f"{'='*70}")
        
        # Show current skill being assessed
        entry = engine._current_skill_entry()
        if entry:
            print(f"[Current Skill: {entry['skill']} | Angle: {entry.get('angle', 'N/A')}]")
            print(f"[Turns on this skill: {entry.get('turns_spent', 0)}/{2}]")
        
        print(f"\n👤 Candidate: {answer[:100]}...")
        
        # Process turn
        result = await engine.process_turn(answer)
        
        # Show score
        se = result.score_entry
        print(f"\n[Score: {se.get('score', 0)}/10 | Skill Area: {se.get('skill_area')} | Action: {se.get('action')}]")
        if se.get("forced_switch"):
            print("[⚠️ FORCED TOPIC SWITCH by Python — skill exhausted]")
        
        print(f"\n🔵 ARIA: {result.aria_text}")
        
        if result.should_end:
            print("\n[Interview ended — max questions reached]")
            break
    
    # Show final state
    print("\n" + "=" * 70)
    print("INTERVIEW SUMMARY")
    print("=" * 70)
    print(f"Questions asked: {engine.state.question_count}")
    print(f"Skills covered: {engine.state.covered_skill_areas}")
    print(f"Scores:")
    for s in engine.state.scores:
        print(f"  - {s.get('skill_area')}: {s.get('score')}/10")
    
    # Calculate average
    scores = [s.get("score", 0) for s in engine.state.scores if s.get("score", 0) > 0]
    avg = sum(scores) / len(scores) if scores else 0
    print(f"\nAverage Score: {avg:.1f}/10")
    
    print("\n[Simulation complete]")

asyncio.run(main())
