"""
Interactive text-based interview test.
Type your answers instead of speaking.

Usage:
    python test_interactive.py

Commands:
    quit    - Exit the interview
    debug   - Show current skill state
    skip    - Skip with a generic response
"""
import asyncio
import sys
sys.path.insert(0, ".")

from backend.utils.pdf_parser import parse_jd, generate_skill_rules
from backend.interview.engine import InterviewEngine
from backend.interview.state import InterviewState

# Mock resume - edit these to match your actual resume
MOCK_RESUME = {
    "candidate_name": "Kyle Austria",
    "current_role": "Full Stack Developer", 
    "total_experience_years": 3,
    "skills": [
        "PHP", "Laravel", "MySQL", "PostgreSQL", "Redis",
        "Angular", "TypeScript", "JavaScript", "HTML", "CSS",
        "AWS", "Docker", "Git", "REST API", "Eloquent ORM",
        "Vue.js", "Node.js", "Python"
    ],
    "experience": [
        {
            "company": "Clark Outsourcing",
            "role": "Full Stack Developer",
            "duration": "2022 - Present",
            "highlights": [
                "Built internal enterprise systems: payroll, employee management, performance tracking",
                "Used Laravel for API development, business logic, database interaction via Eloquent",
                "Angular frontend with AWS infrastructure"
            ]
        }
    ]
}

JD_PATH = r"c:\Users\Austria\Downloads\b7zOkPMsqDdPrXNLEGmBDuhEbMzWHdfAqLJiCknG.pdf"


async def main():
    print("\n" + "=" * 60)
    print("  ARIA Interactive Interview Test")
    print("  Type your answers - no speaking required!")
    print("=" * 60)
    
    # Parse JD
    print("\n[Parsing JD...]", end=" ", flush=True)
    jd = await parse_jd(JD_PATH)
    print(f"Done! Role: {jd.get('job_title')}")
    
    # Generate skill rules
    print("[Generating skill rules...]", end=" ", flush=True)
    rules = await generate_skill_rules(jd, MOCK_RESUME)
    print(f"Done! {len(rules)} rules")
    
    # Build state
    state = InterviewState(
        session_id="interactive-test",
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
        max_questions=8,
    )
    
    engine = InterviewEngine(state)
    engine.build_interview_context()
    
    # Show skill queue
    print("\n" + "-" * 60)
    print("SKILLS TO COVER:")
    for i, entry in enumerate(engine._skill_queue[:8]):
        print(f"  {i+1}. {entry['skill']}")
        print(f"     Angle: {entry.get('angle', 'general')}")
    print("-" * 60)
    
    print("\nCommands: 'quit' to exit, 'debug' for state, 'skip' to skip")
    print("-" * 60)
    
    # Generate greeting
    print("\n[ARIA thinking...]")
    greeting = await engine.generate_greeting()
    print(f"\n🔵 ARIA: {greeting}\n")
    
    turn = 0
    while not engine.state.is_complete:
        turn += 1
        
        # Show current skill context
        entry = engine._current_skill_entry()
        if entry:
            print(f"[Skill: {entry['skill']} | Angle: {entry.get('angle', 'N/A')} | Turn {engine.state.question_count}/{engine.state.max_questions}]")
        
        # Get input
        try:
            answer = input(f"\n👤 You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[Interrupted]")
            break
        
        if not answer:
            continue
        
        if answer.lower() == "quit":
            print("\n[Interview ended by user]")
            break
        
        if answer.lower() == "debug":
            print(f"\n[DEBUG STATE]")
            print(f"  Question count: {engine.state.question_count}/{engine.state.max_questions}")
            print(f"  Current skill idx: {engine._current_skill_idx}")
            print(f"  Current skill: {engine._current_skill()}")
            if entry:
                print(f"  Turns spent: {entry.get('turns_spent', 0)}/2")
                sq = entry.get('sample_question', '')
                print(f"  Sample Q: {sq[:60]}..." if len(sq) > 60 else f"  Sample Q: {sq}")
            print(f"  Covered areas: {engine.state.covered_skill_areas}")
            print(f"  Scores: {[(s.get('skill_area'), s.get('score')) for s in engine.state.scores]}")
            continue
        
        if answer.lower() == "skip":
            answer = "I'm not very familiar with that, can we move on to the next topic?"
            print(f"  → {answer}")
        
        # Process
        print("\n[ARIA thinking...]")
        result = await engine.process_turn(answer)
        
        # Show score
        se = result.score_entry
        score = se.get('score', 0)
        skill = se.get('skill_area', '?')
        action = se.get('action', '?')
        forced = " (FORCED)" if se.get('forced_switch') else ""
        
        if score > 0:
            print(f"[Score: {score}/10 | Skill: {skill} | Action: {action}{forced}]")
        
        print(f"\n🔵 ARIA: {result.aria_text}\n")
        
        if result.should_end:
            print("\n" + "=" * 60)
            print("INTERVIEW COMPLETE")
            print("=" * 60)
            
            # Quick verdict
            engine.state.logistics_raw = [
                {"question": "Availability?", "answer": "Can start in 2 weeks"},
                {"question": "Salary?", "answer": "Flexible, around 50-60k"},
            ]
            
            print("\n[Generating verdict...]")
            verdict = await engine.generate_verdict()
            
            print(f"\nVerdict: {verdict.get('overall_verdict', 'N/A')}")
            print(f"Score: {verdict.get('overall_score', 0)}/10")
            print(f"Recommendation: {verdict.get('recommendation', 'N/A')}")
            
            print("\nSkill Scores:")
            for s in engine.state.scores:
                if s.get('score', 0) > 0:
                    print(f"  - {s.get('skill_area')}: {s.get('score')}/10")
            break
    
    print("\n[Test complete]")


if __name__ == "__main__":
    asyncio.run(main())
