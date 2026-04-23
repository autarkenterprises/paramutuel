The following describe certain mandatory software development practices, to enshrine well-skilled methodologies:

1. Follow strict red-green Test Driven Design - tests must precede code, and tests must provide feedback both when code is absent (tests must fail), and present (tests must pass). Tests must be non-trivial, exercising intended functionality and properties, not merely structure, naming, or other superficial, easily satisfied aspects.

2. Test coverage must be total, and if not, documented as such, with sufficient rationale to excuse total coverage of all code paths. 

3. Comment all code thoroughly, sufficient that the codebase might be transferred to another developer who, though competent, is entirely unfamiliar with the software, its rationale, and its history.

4. Architecture Decision Records must precede all feature implementation - these document the motivations, decision points, and success/failure criteria for each feature, and the project design document should map to a sequence of ADRs. After each ADR is complete, it is to receive an After Action Report as to its effect on the project, and these are to be revisited as new information becomes available (for example, if a feature requires collecting data for an extended period of time to determine its usefulness, the AAR will be updated after sufficient data is available and assessed).

5. Branch discipline should generally follow the ADR structure of the implementation roadmap, with a new branch for each ADR, merged into master once the feature is complete, or development otherwise halted. 

6. Commit only those files one specifically has intentionally modified, and push after every logical unit of work is complete (which implies a passing, regression free test suite evaluation).

7. Do not regress code, or change unrelated elements, aspects, or the structure of the codebase, in the pursuit of a given objective. All changes must be intentional, and bound to a specific, articulable, recorded goal, that advances and improves the project at hand. Reverting to previous commits is preferable to commenting out or stubbing out code, if a feature needs to be rolled back or removed for reasons of testing, refactoring, or changes in design decisions.

8. Eagerly and assiduously seek out tasks and complete them; do not stop or defer work for later. Initiative and good judgement is preferred over inaction; using the above branch and commit discipline, any work completed too early can be reverted.

9. Ask questions freely, where clarification is needed, but do not ask for a second opinion merely out of caution - if you have made the right decision, be confident in its correctness, and carry it out.

10. Review these practices reguarly, to keep them in context.

11. Separate slower recursive, reverse, and partial-synthesis regressions into an explicit extended suite rather than placing them on the default fast path. For this repository, use `lein test-proflog-fast` for the normal greenfield regression path, and `lein test-proflog-extended` for the deeper recursive and synthesis probes.

12. Do not neglect the extended suite: run `lein test-proflog-fast` and `lein test-proflog-extended` in parallel while doing active semantic work, but only block on the extended suite after major revisions or before a commit that changes proof search, equality, negation, or query behavior.

13. Prefer the Clojure MCP tools and the project nREPL for semantic investigation, targeted evaluation, and long-running proof probes. Use shell timeouts and ad hoc scripts only as secondary support when the MCP/nREPL path is insufficient.
