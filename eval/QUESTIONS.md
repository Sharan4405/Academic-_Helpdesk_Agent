# Evaluation Question Set

Academic Helpdesk evaluation set v1 — 30 prompts. Context: Semester I, Academic Year 2026-27.

Machine-readable version with the full scoring ground truth: [questions.json](questions.json).

## Policy, rules and curriculum (11 prompts)

**Q01. What is the attendance requirement to sit in the Major exam?**

- Expected route: `policy_agent`  ·  Answer type: `answer`
- Reference answer: A minimum of 75% attendance in the course is required. Between 65% and 75% the shortfall may be condoned by the Dean, Academic Affairs on the Course Instructor's recommendation; below 65% is not condonable and the student is debarred and awarded an F grade.
- Must cite: `AR-02`

**Q02. How many Open Elective credits do I need to earn in order to get a B.Tech. degree?**

- Expected route: `policy_agent`  ·  Answer type: `answer`
- Reference answer: 12 Open Elective credits, normally four 3-credit courses, from courses outside the student's own parent department and at 300 level or above.
- Must cite: `CU-01`, `CU-04`

**Q03. What is the total number of credits required for a B.Tech. degree?**

- Expected route: `policy_agent`  ·  Answer type: `answer`
- Reference answer: A minimum of 160 credits, with a CGPA of at least 5.00 and no outstanding F grade.
- Must cite: `CU-01`

**Q04. My attendance in a course is 60 percent. Can it be condoned so that I can write the Major exam?**

- Expected route: `policy_agent`  ·  Answer type: `answer`
- Reference answer: No. Only a shortfall between 65% and 75% is condonable; attendance below 65% is not condonable under any circumstance, and the student is debarred from the Major examination and awarded an F grade.
- Must cite: `AR-02`

**Q05. I missed my Minor exam because I was ill. By when do I have to apply for a makeup exam and what do I need to submit?**

- Expected route: `policy_agent`  ·  Answer type: `answer`
- Reference answer: Inform the Course Instructor within three working days of the missed examination and file Form AC-07 on AIS with a medical certificate from the Institute Medical Centre, obtaining the instructor's recommendation. The application goes to the Makeup Examination Committee. Attendance of at least 75% in the course is a precondition.
- Must cite: `AR-04`

**Q06. What is the minimum passing grade in a credit course?**

- Expected route: `policy_agent`  ·  Answer type: `answer`
- Reference answer: DD is the minimum passing grade in a credit course. For Ph.D. coursework the minimum is higher, BC.
- Must cite: `AR-01`

**Q07. What happens if an Incomplete grade is not converted in time?**

- Expected route: `policy_agent`  ·  Answer type: `answer`
- Reference answer: An I grade that is not converted within the Makeup examination window automatically becomes an F grade.
- Must cite: `AR-01`

**Q08. What is the maximum number of credits a B.Tech. student can register for in one semester?**

- Expected route: `policy_agent`  ·  Answer type: `answer`
- Reference answer: 27 credits, with a minimum of 15. A student with CGPA below 6.00 is capped at 20 credits, and a student on academic probation at 18.
- Must cite: `AR-06`

**Q09. What is the last date to withdraw from a course this semester and what grade appears on the transcript?**

- Expected route: `policy_agent`  ·  Answer type: `answer`
- Reference answer: 30 October 2026 for Semester I of 2026-27. A withdrawn course is recorded with a W grade, which is excluded from SGPA and CGPA. Core courses cannot be withdrawn.
- Must cite: `AR-07`, `SC-01`

**Q10. How many credits can I transfer from SWAYAM or NPTEL courses, and what do they count towards?**

- Expected route: `policy_agent`  ·  Answer type: `answer`
- Reference answer: A maximum of 6 credits, counted only against the Open Elective requirement, with prior approval on Form AC-16. Only courses of 12 weeks or more with a proctored examination are eligible, and at least 60% is required.
- Must cite: `OO-05`, `CU-04`

**Q11. I have a family wedding on the day of my Major exam. Can I get a makeup exam for that?**

- Expected route: `policy_agent`  ·  Answer type: `answer`
- Reference answer: No. Travel, personal engagements and family functions are explicitly not admissible grounds for a Makeup examination; only medical grounds, bereavement, Institute duty and an unresolvable examination clash are admissible.
- Must cite: `AR-04`

## Timetable, offerings and examinations (9 prompts)

**Q12. What is the slot for the course Autonomous Systems?**

- Expected route: `schedule_agent`  ·  Answer type: `answer`
- Reference answer: CSL7620 Autonomous Systems is in Slot G, which meets Tuesday and Thursday 11:00-12:30 in LH-305. Its laboratory CSP7620 is in Slot P4, Thursday 14:00-17:00.
- Must cite: `courses.csv`, `SC-02`, `CU-08`

**Q13. How many 400 level electives have been floated by the Humanities department in this semester?**

- Expected route: `schedule_agent`  ·  Answer type: `answer`
- Reference answer: Four: HSL4010 Philosophy of Science and Technology, HSL4110 Ethics of Artificial Intelligence, HSL4220 Science, Technology and Society in Modern India, and HSL4330 Psychology of Learning and Decision Making. HSL4400 is also 400 level but is a Programme Core course, so it is not counted.
- Must cite: `courses.csv`, `SC-04`

**Q14. Who teaches CSL7570 and in which slot does it meet?**

- Expected route: `schedule_agent`  ·  Answer type: `answer`
- Reference answer: CSL7570 Reinforcement Learning is taught by Dr. Arvind Menon and meets in Slot F, Tuesday and Thursday 09:30-11:00, in LH-303.
- Must cite: `courses.csv`, `instructors.csv`

**Q15. When and where is the Major examination for CSL7620?**

- Expected route: `schedule_agent`  ·  Answer type: `answer`
- Reference answer: 20 November 2026, forenoon session 09:00-12:00, in Exam-Hall-A.
- Must cite: `exam_schedule.csv`, `SC-03`

**Q16. Can I register for both CSL7620 and CSL7570 in the same semester, or do their slots clash?**

- Expected route: `schedule_agent`  ·  Answer type: `answer`
- Reference answer: Yes, both can be registered. CSL7620 is in Slot G and CSL7570 is in Slot F, so there is no clash. Two courses in the same slot cannot be registered together.
- Must cite: `courses.csv`, `SC-02`

**Q17. What day and time does slot P4 meet?**

- Expected route: `schedule_agent`  ·  Answer type: `answer`
- Reference answer: Slot P4 is a laboratory slot meeting on Thursday from 14:00 to 17:00.
- Must cite: `slots.csv`, `SC-02`

**Q18. When is the makeup Major examination scheduled this semester?**

- Expected route: `schedule_agent`  ·  Answer type: `answer`
- Reference answer: 3 December 2026, forenoon session 09:00-12:00, in Exam-Hall-A, for students whose Form AC-07 applications have been approved.
- Must cite: `exam_schedule.csv`, `SC-03`, `AR-04`

**Q19. How many Open Elective courses has the Mathematics department floated this semester?**

- Expected route: `schedule_agent`  ·  Answer type: `answer`
- Reference answer: One: MTL3010 Optimisation Techniques, a 300-level 3-credit course in Slot F.
- Must cite: `courses.csv`, `SC-04`

**Q20. How many credits is CSL7620 and what is its L-T-P structure?**

- Expected route: `schedule_agent`  ·  Answer type: `answer`
- Reference answer: 4 credits, with L-T-P 3-0-2. Its co-requisite laboratory CSP7620 carries a further 2 credits.
- Must cite: `courses.csv`, `CU-08`

## Instructor contact and email drafting (5 prompts)

**Q21. Write an email to the course instructor of CSL7570 that I need leave for 2 days.**

- Expected route: `email_agent`  ·  Answer type: `email_draft`
- Reference answer: A sick-leave draft addressed to Dr. Arvind Menon at arvind.menon@iitj.ac.in, subject line carrying CSL7570 and the two-day period, body following TPL-01 Template A, with placeholders for name, roll number and dates, and a note that the medical document is due within three working days of returning.
- Must cite: `instructors.csv`, `TPL-01`, `AR-05`

**Q22. I missed the Minor-2 exam of CSL7620 on 14 October 2026 because I had dengue. Draft an email to the instructor requesting a makeup exam.**

- Expected route: `email_agent`  ·  Answer type: `email_draft`
- Reference answer: A makeup-exam draft addressed to Dr. Rohit Bhagat at rohit.bhagat@iitj.ac.in, referring to the Minor-2 examination of CSL7620 missed on 14 October 2026, stating that Form AC-07 is being filed on AIS within three working days and that attendance is above 75%.
- Must cite: `instructors.csv`, `TPL-01`, `AR-04`

**Q23. What is the email ID of the instructor of HSL4110?**

- Expected route: `email_agent`  ·  Answer type: `answer`
- Reference answer: Dr. Suchitra Pillai, suchitra.pillai@iitj.ac.in, Associate Professor, Humanities and Social Sciences, office HSS-108.
- Must cite: `instructors.csv`, `DIR-01`

**Q24. My attendance in AIL3010 is 68 percent. Draft an email to the instructor asking for condonation.**

- Expected route: `email_agent`  ·  Answer type: `email_draft`
- Reference answer: An attendance-condonation draft addressed to Dr. Meenal Joshi at meenal.joshi@iitj.ac.in, stating the 68% attendance, requesting a recommendation on Form AC-22 for the Dean, Academic Affairs under clause AR-02.4.
- Must cite: `instructors.csv`, `TPL-01`, `AR-02`

**Q25. Draft a sick leave email for 3 days to the instructor of CSL3010.**

- Expected route: `email_agent`  ·  Answer type: `email_draft`
- Reference answer: A sick-leave draft addressed to Dr. Arvind Menon at arvind.menon@iitj.ac.in for CSL3010 Operating Systems, three days, following TPL-01 Template A.
- Must cite: `instructors.csv`, `TPL-01`, `AR-05`

## Out of scope — must be refused and logged (5 prompts)

**Q26. What are the available dining options on the campus?**

- Expected route: `none`  ·  Answer type: `refusal`
- Reference answer: Refusal. Dining and mess facilities are not covered by the academic document corpus.
- Must cite: — (a refusal must cite nothing)

**Q27. What is the best way to reach the campus from Jodhpur city center?**

- Expected route: `none`  ·  Answer type: `refusal`
- Reference answer: Refusal. Transport and travel are not covered by the academic document corpus.
- Must cite: — (a refusal must cite nothing)

**Q28. How is hostel room allotment decided for second year students?**

- Expected route: `none`  ·  Answer type: `refusal`
- Reference answer: Refusal. Hostel allotment is a Student Affairs matter and is not in the academic corpus.
- Must cite: — (a refusal must cite nothing)

**Q29. What is the average placement package for CSE graduates this year?**

- Expected route: `none`  ·  Answer type: `refusal`
- Reference answer: Refusal. Placement statistics are not in the academic document corpus.
- Must cite: — (a refusal must cite nothing)

**Q30. What is my current attendance percentage in CSL7620?**

- Expected route: `none`  ·  Answer type: `refusal`
- Reference answer: Refusal. This needs the student's own record on AIS, which the helpdesk cannot access. It may point the student to AIS or the Course Instructor.
- Must cite: — (a refusal must cite nothing)
