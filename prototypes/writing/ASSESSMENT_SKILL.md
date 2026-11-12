# Writing Task 2 assessment procedure

This file documents the application skill. It is not registered as a Codex skill.
Framework-specific skill registration must be agreed with the group/course.

1. Validate the question and immutable original essay; reject empty input.
2. Call get_writing_rubric; live mode requires a versioned official rubric.
3. Run A and B independently, without sharing their outputs.
4. Validate criterion coverage, score domain, exact quotes and rubric references.
5. Feed validation errors back to that judge; at most two repair attempts.
6. Compare valid assessments. Criterion difference >=1.0 invokes moderator.
7. Validate moderator output. A failure never creates a public score.
8. Aggregate without intermediate rounding; round task estimate once using the
   app's half-up policy. This is an app policy, not a claim of official scoring.
9. Extract at most two supported corrections; validate quotes before persistence.
10. Call save_writing_errors idempotently. Record result and validation trace.

Demo scores are fixed fixtures, never learner estimates. A third model does not
guarantee correctness. Teacher workflow and Planning integration remain external.
