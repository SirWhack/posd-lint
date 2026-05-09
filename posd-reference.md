# A Philosophy of Software Design — Working Reference

A working reference distilled from John Ousterhout's *A Philosophy of Software Design* (1st ed. 2018, 2nd ed. 2021), structured for use across an entire project rather than as a chapter summary. Both editions in scope; 2nd-edition-only material is flagged inline.

For each concept: Ousterhout's framing (in his words where the wording is load-bearing), the diagnostic question, and the most common mistake. The closing appendices give a unified red-flag catalog, the Ousterhout-vs-Martin (Clean Code) deltas, and four cross-cutting lenses (new module / refactor / code review / self-review).

Source confirmation throughout: book TOC for both editions, Ousterhout's Stanford CS 190 lecture notes, the public Ousterhout/Martin debate, and the 2nd-edition extract Ousterhout published. Citations at the end.

---

## Part I — Foundations

## 1. The nature of complexity (Ch. 1–2)

Ousterhout's working definition: complexity is *"anything related to the structure of a system that makes it hard to work on the development of that system."* It is **apparent**, not theoretical — *"what a developer experiences at a particular moment"* matters more than what a theorist can prove.

Three symptoms (any one is sufficient evidence):

- **Change amplification** — *"a simple change requires many code modifications."*
- **Cognitive load** — you *"have to load a lot of information in your mind in order to make a change."*
- **Unknown unknowns** — *"there's important information you need to know before making a change, but [it's] not obvious where to find it."* Ousterhout calls this the worst of the three: the others you can see; this one you trip on.

Two root causes underneath every symptom:

- **Dependencies** — *"one piece of code is tightly coupled with another."* You cannot change A without considering B.
- **Obscurity** — *"not clear how things work or why the code is the way it is."* The opposite is *obvious*: *"a developer's first guess about how it works or what to do will be correct."*

Complexity is **incremental**. *"No one thing makes a system complicated"* — it is *"an accumulation of thousands of small dependencies and obscurities."* Once present it is *"hard to eliminate,"* which forces a *"zero-tolerance attitude: everything matters."* The book's whole stance flows from this: design is an exercise in not letting complexity in, one decision at a time.

- **Diagnostic:** for any code you've just written, run all three symptom checks. "If a peer changed this in six months, would the change ripple? Would they need context that isn't in this file? Would their first guess be right?"
- **Most common mistake:** treating complexity as a thing to clean up in a future refactor. The book's central claim is that you cannot refactor your way out of a thousand small obscurities; the only winning move is not to admit them in the first place.

## 2. Strategic vs. tactical programming (Ch. 3)

Two stances toward the work:

- **Tactical** — *"Goal is to get the next feature or bug fix working. A few shortcuts and kludges are OK, if it gets things done quickly."* Optimises for the next demo; pays interest forever after.
- **Strategic** — *"How easy is it to evolve this code?"* is the controlling question. You produce working code *and* a system that can absorb the next change without ceremony.

The **tactical tornado** is Ousterhout's archetype of the productive-looking individual whose output makes the system worse: ships features fast, leaves wreckage that everyone else has to live in. They are often praised by management because the cost is paid by their colleagues, not by them.

His investment claim: *"10–20% overhead"* on design pays back in *"6–12 months."* Not 1%; not 50%. Enough that you feel the slowdown, little enough that the payback period is measured in months.

- **Diagnostic:** ask, on every PR, "did this leave the design better than I found it, or just working?" If only working, you took a tactical step. A few are fine. A career of them is a tactical tornado.
- **Most common mistake:** confusing iteration with tactical. Ousterhout is not against iteration — he is against shipping kludges and never coming back. The strategic equivalent is: ship, observe, redesign. Agile *can* be strategic; TDD-style "tiny green steps forever" tend not to be (see §18).

## 3. Design it twice (Ch. 11)

The discipline: for any non-trivial design decision, sketch *at least two* candidate designs *before* committing. *"Try to pick approaches that are radically different from each other; you'll learn more that way."* Even when you are sure there is only one reasonable approach, do a second one anyway, *"no matter how bad you think it will be"* — the bad one teaches you what the good one is for.

The cost is small (a sketch, not an implementation). The return is the contrast: you don't see the weakness of your first design until you can hold it next to a different one. Ousterhout cites his own work on the Tk toolkit's API as the canonical example — the second design was clearly better, and he wouldn't have known the first was deficient without it.

- **Diagnostic:** if you can name only one viable design for the thing you're about to build, you haven't designed it yet — you've just had an idea. *"Radically different"* means different decomposition, not different syntax.
- **Most common mistake:** "design it twice, but the second design is just the first with the names changed." That isn't a contrast, it's a re-typing. The second design has to differ at the joints — different module boundaries, different ownership of state, different layering — for the comparison to teach you anything.

---

## Part II — Modules and Interfaces

## 4. Modules and interfaces (Ch. 4.1–4.3)

A **module** is a unit of code "relatively independent" of others. Its **interface** has two parts:

- **Formal interface** — method signatures, public variables, types.
- **Informal interface** — overall behaviour, side effects, ordering constraints, thread-safety, error semantics. *"Informal aspects can only be described with comments."*

**Abstraction** is *"a simplified view of something that omits unimportant details."* A module's interface *is* its abstraction. The goal is to *"define simple abstractions that provide rich functionality."*

- **Diagnostic:** what does a caller need to know to use this module correctly? Is all of that in the formal signature, or is some of it tribal knowledge / required call ordering / "you have to construct X before Y"?
- **Most common mistake:** treating the formal signature as the whole interface. Side effects, mutation, required ordering, and exception types are part of the contract whether you document them or not.

## 5. Deep vs. shallow modules (Ch. 4.4–4.6)

The depth metaphor: a module is a rectangle. Width = interface surface area (how much a user must learn). Area = total functionality. **Depth = area / width.** Deep is good.

- **Deep:** small interface, lots of functionality, lots of information hidden (Unix file I/O — five calls hide an entire filesystem).
- **Shallow:** *"Complex interface and/or not much functionality. Invoking a method isn't much easier than just typing in the code of the method."*

Recognising shallow modules:
- Wrapper classes that mostly forward to a delegate.
- Methods whose signature is as wide as the body (`def set_x(self, x): self.x = x`).
- Classes whose public surface tells you exactly what fields are inside.

**Classitis** is Ousterhout's name for the cult of small classes — the belief that "classes should be small" pushed past the point where each new class adds more interface than it hides. The Clean Code "small functions" principle is its method-level cousin (see Appendix B).

- **Diagnostic:** *"Is invoking this method materially easier than inlining its body?"* If no, the module isn't paying for its interface.
- **Most common mistake:** splitting a class because it "feels too big," producing two shallow classes whose combined interface is wider than the original.

## 6. Information hiding vs. information leakage (Ch. 5)

**Information hiding:** each module encapsulates a design decision; only that module knows it; the implementation can change without rippling.

**Information leakage:** *"a design decision is reflected in multiple modules"* — the same fact has to be known in two places, so changing it requires editing both. Anything in the formal interface is leaked by definition; the goal of design is to minimise what has to leak.

**Temporal decomposition** is the flagship leakage anti-pattern: structuring code so each module corresponds to a phase of execution (read → parse → process → write). Adjacent phases end up sharing format knowledge, so the same design decision (the file format, the protocol layout) is now smeared across modules. *"One of the most common causes of information leakage."*

Other leakage forms:
- **Back-doors / configuration knobs** that expose internal state.
- **Shared types** that force callers to import the module's internal vocabulary.
- **Required call ordering** (`open()` before `read()` before `close()` with no enforcement).

- **Diagnostic:** *"If this design decision changed, how many modules would I have to edit?"* More than one = leak.
- **Most common mistake:** organising by *when* things happen rather than by *what knowledge* is needed. Pipelines and ETL stages are notorious.

## 7. General-purpose vs. special-purpose (Ch. 6) — *expanded in 2nd ed.*

The rule: **"somewhat general-purpose."** Not maximally generic (you cannot predict future use) and not narrowly specialised to today's one caller (the API will encode caller-specific details and break under the second caller).

The questions Ousterhout names:
- *"What is the simplest interface that will cover all my current needs?"* — fewer methods is better, provided each method gets deeper.
- *"In how many situations will this method be used?"* — methods used in only one place are suspect.
- *"Is this API easy to use for my current needs?"* — generality must not destroy ergonomics.
- *"Does the API have to specialise for the current use, or can it stay general?"*

Generality tends to *improve* information hiding: a general API forces you to stop describing the caller's workflow in the signature.

- **Diagnostic:** does the method name embed a caller's use case (`get_tickets_for_step_panel_render()`)? Specialise the *caller*, not the API.
- **Most common mistake:** writing the API to fit today's single caller (over-specialising), then later bolting on flags for the second caller. Result: a shallow, special-purpose interface with configuration creep.

## 8. Different layer, different abstraction (Ch. 7)

Adjacent layers should provide *different* abstractions. If layer N looks like layer N±1, the layer is not earning its keep.

Red flags:
- **Pass-through methods** — *"a pass-through method is one that does nothing except pass its arguments to another method, usually with the same API."* The boundary between the two classes is in the wrong place.
- **Pass-through variables** — a piece of data threaded through several layers that don't use it, just so a deep layer can reach it. The middle layers now know about something irrelevant to their abstraction. (Ousterhout suggests context objects; some reviewers push back — see Appendix B.)
- **Decorator overuse** — each decorator that just adds a little to the wrapped object usually makes things shallower; consider folding into the underlying class or making a peer class.
- **Interface duplication without added abstraction** — sometimes legitimate (a `Dispatcher` exposing the same `dispatch()` shape as its delegates), but only when the wrapper is itself adding a real abstraction (uniform routing).

- **Diagnostic:** *"What new vocabulary does this layer introduce?"* If "none, it just calls down," the layer is a candidate for collapse.
- **Most common mistake:** introducing a layer "for separation of concerns" that simply forwards. The concerns weren't actually separated; the call stack just got taller.

## 9. Pull complexity downward (Ch. 8)

*"It's more important for a module to have a simple interface than a simple implementation."* The author of the module should absorb pain so that N callers don't each pay it.

The archetype example: **configuration parameters as a code smell.** A configuration parameter is the module saying "I don't know the right value, you figure it out." But the user has *less* information than the module does. Prefer to compute the value internally (e.g. measure RTT to derive a retry interval rather than expose `retry_interval_ms`).

Legitimate configuration: when the *policy* genuinely belongs to the caller (timeouts the caller's SLA dictates, feature flags). Illegitimate: tuning knobs that exist because the author didn't want to decide.

A related framing Ousterhout uses: *"look for opportunities to take a little bit of extra suffering upon yourself to reduce the suffering of your users."* Retry logic absorbed inside an API client; auto-reconnect inside a transport; migrations inside an ORM. The author pays once; every caller benefits.

- **Diagnostic:** for every config parameter, ask: *"Does the caller actually have information that lets them set this better than the module could?"* If no, the module owes it an internal default — or better, an internal computation.
- **Most common mistake:** exposing options to "give callers flexibility." Almost always this is the module pushing its uncertainty upward.

## 10. Better together or better apart (Ch. 9)

Combine when:
1. **Information is shared** — both pieces depend on the same design decision (file format, schema, protocol). Splitting causes leakage.
2. **The combined interface is simpler** — e.g. removing a method that only existed to bridge the two halves.
3. **There is duplication** — the same logic appears in both, and a unified module would absorb it.
4. **They are always used together** — one is meaningless without the other.

Split when:
1. **General-purpose mixed with special-purpose** — extract the general core (the most important rule; this is the "deep general module + thin specialisation" pattern).
2. **Different abstractions** — they happen to share a class but conceptually live at different levels.
3. **Different change rates** for unrelated reasons.

A note on length: Ousterhout is *not* anti-long-method. He explicitly argues against the Clean Code rule that methods should be ~3 lines: *"once a function gets down to a few dozen lines, further reductions in size are unlikely to have much impact on readability. More functions means more interfaces to document and learn."* If two short methods are tightly entangled — one cannot be understood without the other — they were one method that got cut in half.

- **Diagnostic:** *"If I changed X here, would I also have to change Y there?"* Yes → merge. *"Is one half meaningful without the other?"* No → merge. *"Do these two halves share* no *design decision?"* → split.
- **Most common mistake:** splitting because a file got long. Length is the weakest signal; shared design decisions trump it.

## 11. Define errors out of existence (Ch. 10)

*"Reducing the number of exceptions that have to be handled is one of the best techniques for reducing complexity."* The fewer error paths in the interface, the deeper the module.

Techniques:
- **Redefine semantics** so the error can't happen. `unset(key)` succeeds whether or not the key exists — postcondition is "key is not in the map," which is true either way. `substring(start, end)` clips out-of-bounds rather than throwing.
- **Mask at a low level** where the module has the information to handle it (TCP retransmits internally rather than exposing packet loss).
- **Aggregate** error handling — one place that knows what to do, not every caller.

What it isn't: ignoring errors, catching-and-swallowing, returning sentinel values that callers must check. The point is to make the abstraction *truthful* about a smaller set of failure modes, not to hide real ones.

- **Diagnostic:** for each `raise` in the module, ask *"could the postcondition be redefined so this isn't an error?"* or *"could this be handled here rather than reported?"*
- **Most common mistake:** treating exceptions as defensive engineering — "more `raise` = more rigorous." Each exception added to the interface widens it; programmers think they're tightening it.

---

## Part III — Comments and Names

## 12. Why write comments at all (Ch. 12–13)

Ousterhout takes the unusual position that **comments are part of the interface**. The formal signature cannot express invariants, units, side effects, threading, or error contracts; comments encode those. *"Code alone can't represent cleanly all the information in the mind of the designer."*

He systematically dismantles the four standard objections:

| Excuse | Rebuttal |
|---|---|
| *"Good code is self-documenting."* | Self-documenting code conveys *what*, not *why*; not *invariants*; not *failure modes*. The claim mistakes one mode for the whole. |
| *"I don't have time to write comments."* | The cost of writing is amortised over every reader for the life of the code. Skipping is a transfer of cost from author to readers, not a saving. |
| *"Comments get out of date."* | Some do. Most don't, when kept near the code they describe. The fix is proximity and review discipline, not abolition. |
| *"The comments I have seen are worthless."* | Then write better ones. The existence of bad comments doesn't argue against good ones any more than bad code argues against code. |

The categories that matter:
- **Interface comments** — *what someone needs to know in order to use this class or method.* Invariants, units, side effects, threading, error semantics.
- **Implementation comments** — *how the method or class works internally.* Different audience (maintainers, not callers), different content.
- **Cross-module / data-structure comments** — design decisions that touch several places, plus comments on field meanings that callers can rely on.

Ousterhout's rules:
- *"Document each thing exactly once: don't duplicate documentation (it won't get maintained)."*
- *"Put documentation as close as possible to the relevant code."*
- *"Don't say anything more in documentation than you need to."*
- *"Implementation documentation contaminates the interface when interface documentation describes implementation details that aren't needed in order to use the thing being documented."*

The structural test: *"If it's hard to find a simple name for a variable or method that creates a clear image of the underlying object, that's a hint that the underlying object may not have a clean design."* Comments and names are diagnostic instruments for the design itself; if they fight you, the abstraction is wrong.

- **Diagnostic:** *"If I deleted the comment, what would a caller misuse?"* That's the load-bearing content. Anything else is noise.
- **Most common mistake:** comments that paraphrase the code (`# increment counter` above `counter += 1`). They add tokens, not abstraction. The actual interface contract — *"this method is not idempotent; calling it twice double-counts"* — is the missing thing.

## 13. Choosing names (Ch. 14)

*"Goal: create an image in the mind of the reader."* Two criteria, both required:

- **Precision** — *"as much information as possible in a few words (but not too long)."* `block` could be a memory block, a network block, a UI block; the precise name is the one that rules out the wrong reading.
- **Consistency** — *"always use the same variable name for the same kind of object."* And the inverse: *"avoid using the same name to refer to different kinds of things."* Repurposing variables for a second meaning is information leakage in name-space.

Short names are fine for tight scopes (`i` in a five-line loop). Longer scopes need longer names — a useful rule of thumb (Andrew Gerrand): *"the greater the distance between a name's declaration and its uses, the longer the name should be."*

Generic names — `data`, `info`, `result`, `value`, `object`, `manager`, `handler` — are red flags. They convey nothing the reader didn't already know from context, which means the name is doing zero work.

The deepest use of naming is diagnostic: a hard-to-name thing is usually a wrongly-defined thing. If you cannot draw a clean image with a few words, the abstraction is fuzzy. Don't push through; redefine the thing.

- **Diagnostic:** read the name aloud out of context. If a colleague would not be able to guess the type and role of the variable from the name alone, it's underspecified.
- **Most common mistake:** treating naming as a cosmetic last pass. Names *encode* design decisions; renaming exposes design decisions you didn't realise you'd made.

## 14. Write comments first (Ch. 15)

The discipline: write the interface comment *before* writing the method body. Write the class comment before any methods. Write the field comment before the field has a meaning.

The point isn't documentation hygiene — it's design feedback. *"If you find it difficult to write a simple yet complete comment describing something,"* the abstraction is wrong. The comment is a small, cheap test of whether you've actually defined a clean concept; it fails fast, before you've written code that locks in the bad concept.

Concrete benefits Ousterhout names:
- Comments written first are calibrated to the *interface*, because no implementation exists yet to drift toward.
- The cost is roughly free — you would have written the comment eventually; doing it first means you write it once instead of retrofitting.
- It surfaces hard cases (edge conditions, error semantics) before you've committed to a code shape that can't accommodate them.

- **Diagnostic:** before writing a method, write its docstring. If you stall, you don't know what you're building yet — design more before coding.
- **Most common mistake:** writing the comment last as a paraphrase of the code you ended up with. That's documentation, not design feedback. The comment-first version uses the comment to *pressure-test the design*; the comment-last version just records what survived.

---

## Part IV — Working with Code

## 15. Modifying existing code (Ch. 16)

The rule: every change should leave the system *with a better design*, not merely with a working new behaviour. This is the maintenance-mode counterpart of strategic vs. tactical (§2). Tactical edits in existing code are the dominant source of complexity accretion: the bug got fixed, the design got worse, nobody noticed, the next person pays.

When you fix a bug or add a feature:
- Fix it where the right abstraction *would* have caught it, even if the wrong one did. If the bug exists because a module leaked a design decision, the fix is to plug the leak, not patch the symptom at the leak site.
- Update comments alongside the code. Stale comments are worse than missing ones; the modification window is the only moment they get fixed.
- Actively look for opportunities to invest in design within the change. If the area you're touching has a known wart, this is a cheap moment to address it (you're already loaded with context).
- Resist *unrelated* refactoring in the same change — the diff stops being reviewable. Bank the observation, do it next.

- **Diagnostic:** *"If the next person inheriting this area read just my diff, would they understand the design better than before — or only the new behaviour?"*
- **Most common mistake:** the "minimal diff" reflex. Minimising lines changed often means leaving a known design defect in place because fixing it would touch more files. A larger, design-improving diff is usually cheaper to live with than a smaller, design-preserving one.

## 16. Consistency (Ch. 17)

Consistency is *cognitive leverage*: learn one pattern, recognise it everywhere, save the cost of relearning. The categories that matter:

- **Names** — same vocabulary for the same thing across files.
- **Coding style** — formatting, structure, idioms.
- **Interfaces** — similar concepts have similar method shapes.
- **Design patterns** — the same problem solved the same way each time.
- **Invariants** — the same rules hold throughout (e.g. "all timestamps are UTC", "all IDs are strings").

Enforcement, in increasing order of strength: written conventions → linters and code generators → review discipline → "when in Rome…" (newcomers conform to local style by default). Tooling beats discipline; discipline beats nothing; but a written rule that nobody enforces is worse than no rule because it provides false confidence.

The hard rule: *don't redesign existing code just to use a new way.* If the codebase uses pattern A and you've decided pattern B is better, do not sprinkle B across the codebase next to A. Either migrate fully (a project) or stay consistent. Mixed conventions cost more cognitive load than either pure A or pure B.

- **Diagnostic:** can a reader who knows one part of the codebase navigate another part by analogy? If not, you have local conventions but not global consistency.
- **Most common mistake:** the "this part of the codebase is special" argument. It almost never is. Special cases that deviate from house style impose a re-learning cost on every reader who lands there.

## 17. Code should be obvious (Ch. 18)

Obvious = *"the reader's first guess about how it works or what to do is correct,"* and they can confirm without reading carefully. The opposite of obscurity.

Things that make code non-obvious (and therefore complex):
- **Event-driven flow** — control jumps without local evidence; the reader cannot trace from a call site to the handler. (Ousterhout's example; some reviewers note this is unavoidable in modern async/distributed code — accept it where required, treat it as a tax to be minimised.)
- **Generic containers without type information** — `Map<String, Object>` forces the reader to reconstruct the schema by reading callers.
- **Repurposed variables** — a name that means one thing in the first half of a function and another thing in the second half.
- **Code that violates conventions** — the reader's "first guess" comes from convention; deviation forces re-reading.
- **Implicit information** — the function relies on a precondition the caller is responsible for, but the precondition isn't visible at the call site.

Ousterhout's calibration: *"if someone says your code is not obvious, then it isn't."* Obviousness is a property of the reader's experience, not the author's intent. You don't get to argue that it should have been obvious.

- **Diagnostic:** show the function to someone who hasn't seen this code. Does their first reading match the actual behaviour? If not, the code isn't obvious — and you cannot fix it by explaining; you have to change it.
- **Most common mistake:** confusing "I can read it" with "it is obvious." The author always understands their own code. Obviousness is measured by readers, not writers.

---

## Part V — Context and Priorities

## 18. Software trends (Ch. 19) — *significantly expanded in 2nd ed.*

Ousterhout uses this chapter to apply the book's framework to widely-held practices. He approves of some, dissents from others; the framework is consistent throughout (does the practice produce deeper modules and less complexity, or shallower modules and more?).

| Practice | Verdict | Reasoning |
|---|---|---|
| Object-oriented programming | Mixed | Encapsulation is good; *inheritance* tends to entangle subclasses with superclass internals. Composition usually deeper. |
| Agile / iterative development | Conditional good | Iteration is sound; the failure mode is when iterations become tactical (just ship the feature). Iteration must include redesign. |
| Unit tests | **Essential** | They enable *"fearless refactoring"*: structural improvements you wouldn't dare without coverage. The book is unambiguously pro-test. |
| Test-driven development | **Critical** | Quoted below. |
| Design patterns | Use sparingly | Useful as vocabulary; harmful when applied as ritual ("we need a Factory here") rather than because the problem demands it. |
| Getters/setters | Anti-pattern | Most exist because the field shouldn't have been public; they expose the implementation choice rather than hide it. |

The TDD critique is the chapter's load-bearing argument and frequently quoted:

> *"The problem with test-driven development is that it focuses attention on getting specific features working, rather than finding the best design. This is tactical programming pure and simple, with all of its disadvantages."*

> *"TDD is an incremental approach that discourages large-scale thinking about the overall design of the code … you end up coding in a very incremental, local manner that doesn't encourage you to think systemically about the overall design."*

The 2nd edition expands this section: Ousterhout is *for* unit testing (he says so explicitly; see Appendix B), and *against* the specific claim that you should write the test before the design. His position: design first, then write tests against the resulting interface, then iterate.

- **Diagnostic:** for each practice your team uses, ask the framework's question — does it produce deeper modules and less complexity, or shallower and more? Adopt practices on that basis; don't adopt because of authority.
- **Most common mistake:** treating "best practice" as terminal. Every practice in this chapter has a context where it applies and a context where it makes things worse. The book's point is that the *underlying* principle (manage complexity) is what's terminal, not any of the practices.

## 19. Designing for performance (Ch. 20)

The argument: simple code tends to be fast code, because a clean abstraction usually corresponds to a clean computation. Two rules:

1. **Measure first.** Don't optimise without evidence. The hot path is rarely where you guessed.
2. **Once you have evidence, redesign around the critical path.** Not "add a cache here" — *redesign* so the hot path is short and direct, with the slow concerns moved off it. The performance-critical module gets the most design attention; everything else gets the simplest design.

This is consistent with the rest of the book: performance is achieved through *clearer* designs (deeper modules, less indirection on the hot path), not through cleverer ones. Premature optimisation is the small-scale failure mode; clever optimisation that buys 10% at the cost of comprehensibility is the large-scale one.

- **Diagnostic:** before any optimisation, can you point at a profile that shows this code is hot? If not, you're optimising imagination.
- **Most common mistake:** caching as a first instinct. Caching is the most expensive form of complexity (correctness invariants across two stores); reach for it last, after structural redesign of the hot path has been tried.

## 20. Decide what matters (Ch. 21) — *new in 2nd ed.*

The synthesising chapter of the 2nd edition. Software design is *"about separating what's important from what's not important and focusing on what's important."* The chapter is structured as four moves:

- **21.1 How to decide what matters.** What does the abstraction need to communicate? What can a caller *not* afford to misunderstand? Those are the things that matter. Implementation details, internal state, and intermediate steps usually do not.
- **21.2 Minimise what matters.** Even among things that matter, fewer is better. Fewer concepts in the interface, fewer invariants the caller has to track, fewer error modes. *Subtraction* is design.
- **21.3 How to emphasise things that matter.** Position load-bearing concepts where readers will see them: at the top of the file, in the class docstring, in the method's first paragraph, in the name itself. The things that matter should not require excavation.
- **21.4 Mistakes.** The chapter's failure modes: emphasising the wrong things (everything looks important → nothing is); hiding the things that matter behind a flat list of "details"; emphasising things that matter *to the author* (recent decisions, clever bits) rather than things that matter *to the reader*.
- **21.5 Thinking more broadly.** The principle generalises: in any artefact (code, comment, design doc, PR description, talk), decide what matters and put it at the top. Most artefacts fail because they don't.

This chapter is the closest the book comes to an explicit meta-rule. Every previous chapter is an instance of "decide what matters": deep modules emphasise interface over implementation, comments emphasise contract over paraphrase, naming emphasises role over implementation, errors-out emphasises the success path over edge cases.

- **Diagnostic:** for any module, comment, name, or document — what is the *one* thing the reader most needs to take away? Is it where they'll see it first?
- **Most common mistake:** flat structure. A list of ten equally-emphasised facts is a list of zero emphasised facts. If three of the ten matter and seven don't, the artefact has to *say so* — physically, by structure.

---

## Appendix A — Red-flag catalog

A consolidated list of the symptoms the book teaches you to recognise. Each is a hint, not a verdict; investigate before fixing. Quotes are Ousterhout's where the wording is load-bearing.

| # | Red flag | Definition (verbatim or close) | Lives in |
|---|---|---|---|
| 1 | **Shallow module** | *"Interface is complicated relative to the functionality it provides."* | §5 |
| 2 | **Information leakage** | *"The same knowledge is used in multiple places."* | §6 |
| 3 | **Temporal decomposition** | *"Execution order is reflected in the code structure."* | §6 |
| 4 | **Overexposure** | *"The API for a commonly used feature forces users to learn about other features that are rarely used."* | §5, §7 |
| 5 | **Pass-through method** | *"A method that does nothing except pass its arguments to another method, usually with the same API."* | §8 |
| 6 | **Pass-through variable** | A datum threaded through layers that don't use it. | §8 |
| 7 | **Repetition** | *"The same piece of code appears over and over again — you haven't found the right abstractions."* | §10 |
| 8 | **Special-general mixture** | *"A general-purpose mechanism also contains code specialised for a particular use of that mechanism."* | §7, §10 |
| 9 | **Conjoined methods** | *"You can't understand one method without also understanding another."* | §10 |
| 10 | **Configuration parameter as smell** | An option exposed because the module didn't want to decide. | §9 |
| 11 | **Comment repeats code** | *"Comment information is already obvious from the code next to it."* | §12 |
| 12 | **Implementation contaminates interface** | *"Interface documentation describes implementation details not needed to use the thing."* | §12 |
| 13 | **Vague name** | *"A variable or method name is broad enough to refer to many different things."* | §13 |
| 14 | **Hard to pick a name** | *"It's hard to find a simple name — a hint the underlying object may not have a clean design."* | §13 |
| 15 | **Hard to describe** | *"Difficult to write a simple yet complete comment describing something."* | §12, §14 |
| 16 | **Non-obvious code** | *"Meaning and behaviour cannot be understood with a quick reading."* | §17 |
| 17 | **Repurposed variable** | One name, two meanings within a scope. | §13, §17 |
| 18 | **Required call ordering** | API correctness depends on calling A before B, with no enforcement. | §6 |

---

## Appendix B — Ousterhout vs. Martin (Clean Code) — *2nd ed. addition*

The 2nd edition added explicit comparison with *Clean Code*. Ousterhout and Martin held a long public dialogue (linked in sources). Three issues, with Ousterhout's settled positions:

**Method length.** Martin: *"The first rule of functions is that they should be small. The second rule of functions is that they should be smaller than that."* Two-to-four lines is his target. Ousterhout: *"As methods get smaller and smaller there is less and less benefit to further subdivision. The amount of functionality hidden behind each interface drops, while the interfaces often become more complex."* The risk is **entanglement**: methods so small that you cannot understand one without reading three others. Ousterhout's `PrimeGenerator` revision combines Martin's eight tiny methods into one with section comments — and is, on his read, more readable. He concedes that some methods are too long; he denies that small-by-default is a useful rule.

**Comments.** Martin: comments are failures of expression; good code shouldn't need them. Ousterhout: *"There is important information that simply cannot be expressed in code. By adding comments to fill in this missing information, developers can make code dramatically easier to read. This is not a 'failure of their ability to express themselves.'"* He concedes bad comments exist and outdated ones are worse than nothing; he denies that the answer is to abolish them. *"Missing comments cost 10–100× more than incorrect ones."*

**TDD.** Martin: write the test first, in a tight red-green-refactor cycle, in tiny steps. Ousterhout: this *is* tactical programming. He values unit tests (strongly — see §18) but rejects the test-first cadence as a discipline that suppresses large-scale design thinking. Concession: refactoring inside the cycle does help; the discipline isn't worthless. Hold-firm: the cycle's incrementalism is its central flaw, not its supporting feature.

The two men agree on more than the debate suggests — both want code that is easy to change, both think most production code is too complex — but the operational rules differ enough that the books are read as opposing schools. If a team adopts both, it has to choose; the rules conflict at the line-of-code level.

---

## Appendix C — Cross-cutting lenses

Four checklists. Each is a working application of the book's principles to a recurring situation. Designed to be runnable in your head against a diff or a design.

### C.1 New module / new feature

1. **What is the deepest possible interface for this?** Write the docstring before the body (§14).
2. **Which design decisions does this module own?** Those should not appear elsewhere (§6).
3. **Did I sketch a second design?** If not, I have an idea, not a design (§3).
4. **What's the smallest set of methods that covers current need without crippling future use?** "Somewhat general-purpose" (§7).
5. **Every parameter — does the caller actually have better information than I do?** If not, default it or compute it (§9).
6. **Every error path — could the postcondition redefine this away?** (§11).
7. **Do the names create a clear image?** If naming is hard, the abstraction is wrong (§13).
8. **What is the one thing that matters most about this module?** Is it the first thing a reader sees? (§20).

### C.2 Refactor

1. **What design decision is currently leaked across multiple files?** That's the target (§6).
2. **Are there pass-through methods or variables to collapse?** (§8).
3. **Are there shallow classes whose combined interface is wider than they hide?** Merge them (§5, §10).
4. **Is there a general core trapped inside something special-purpose?** Extract (§10).
5. **What's the smallest change that improves the design — not just behaviour?** (§15).
6. **Update or delete comments alongside the change** — stale beats absent (§12, §15).
7. **Resist unrelated refactoring in the same change.** Bank the observation (§15).
8. **After the refactor, can a reader navigate the area by analogy from the rest of the codebase?** (§16).

### C.3 Code review (someone else's diff)

1. **Run the three complexity symptoms against the diff.** Change amplification, cognitive load, unknown unknowns (§1).
2. **Is this tactical or strategic?** A few tactical PRs are fine; flag if pattern (§2).
3. **Pass-through audit** — does this layer add a new abstraction, or just forward? (§8).
4. **Configuration parameter audit** — does the caller really have better information? (§9).
5. **Error-path audit** — every new `raise` widens the interface. Justified? (§11).
6. **Name audit** — generic names (`data`, `result`, `manager`)? Repurposed within a scope? (§13).
7. **Comment audit** — interface comments truthful? Implementation contaminating the interface? (§12).
8. **Obviousness check** — is the first reading correct? If not, request changes regardless of correctness (§17).

### C.4 Self-review (your own diff before sending)

1. **Read the diff as if it were someone else's.** What would you flag?
2. **Did I leave the design better, or only working?** (§2, §15).
3. **Comment-first sanity check** — could I have written the new docstrings before the bodies? If they would have been hard to write, the design is probably wrong (§14).
4. **One-thing test** — for each new module/method, what's the one thing that matters? Is it visible immediately? (§20).
5. **Trim** — anything in the interface that doesn't need to be? Move it down (§9).
6. **Reread the names aloud out of context** (§13).
7. **Check consistency with the rest of the codebase** — same vocabulary, same patterns? (§16).
8. **One more pass for obviousness.** If anything would force a careful re-read, fix it before sending (§17).

---

## Sources

- *A Philosophy of Software Design*, John Ousterhout — 1st ed. (2018) and 2nd ed. (2021). Chapter structure and verbatim quotes drawn from both.
- [Ousterhout, CS 190 — Modular Design lecture (Stanford, Winter 2018)](https://web.stanford.edu/~ouster/cgi-bin/cs190-winter18/lecture.php?topic=modularDesign) — primary source for definitions of interface, abstraction, deep/shallow, classitis, pull-complexity-downward, somewhat-general-purpose, different layer different abstraction.
- [Ousterhout, CS 190 — Complexity lecture](https://web.stanford.edu/~ouster/cgi-bin/cs190-winter18/lecture.php?topic=complexity) — three symptoms (change amplification, cognitive load, unknown unknowns), two root causes (dependencies, obscurity), incrementalism.
- [Ousterhout, CS 190 — Working Isn't Good Enough](https://web.stanford.edu/~ouster/cgi-bin/cs190-winter18/lecture.php?topic=working) — tactical vs. strategic, tactical tornado, 10–20% / 6–12 month investment numbers.
- [Ousterhout, CS 190 — Comments lecture](https://web.stanford.edu/~ouster/cgi-bin/cs190-winter18/lecture.php?topic=comments) — four excuses and their rebuttals, comment categories, the four rules.
- [Ousterhout, CS 190 — Names lecture](https://web.stanford.edu/~ouster/cgi-bin/cs190-winter18/lecture.php?topic=names) — "create an image in the mind of the reader," precision and consistency.
- [Software Design Book (Ousterhout's official page)](https://web.stanford.edu/~ouster/cgi-bin/book.php) — 2nd-edition changes summary direct from the author: new "Decide What Matters" chapter, expanded Ch. 6, Clean Code comparison.
- [Ousterhout/Martin — A Philosophy of Software Design vs. Clean Code (GitHub)](https://github.com/johnousterhout/aposd-vs-clean-code) — primary source for Appendix B; verbatim positions on method length, comments, TDD.
- [Sébastien Portebois — Software Design Red Flags (notes on PoSD)](https://notes.portebois.net/2021/03/04/13.html) — verbatim red-flag definitions used in Appendix A.
- [Marco Bacis — PoSD summary](https://marcobacis.dev/blog/philosophy-of-software-design/) — chapter map, complexity framing, TDD critique paraphrase.
- [Maëlle Salmon — Reading notes on PoSD](https://masalmon.eu/2023/10/19/reading-notes-philosophy-software-design/) — "extra suffering on yourself to reduce suffering of users," Andrew Gerrand naming heuristic.
- [The Pragmatic Engineer — review and Ousterhout interview](https://blog.pragmaticengineer.com/a-philosophy-of-software-design-review/) — chapter coverage, including Ch. 15–18.
- [Matt Duck — Reading notes on PoSD](https://www.mattduck.com/2021-04-a-philosophy-of-software-design.html) — TDD critique sourcing, consistency-as-leverage framing.
- [TCL Wiki — Define Errors Out of Existence](https://wiki.tcl-lang.org/page/Define+Errors+Out+of+Existence) — `unset` and `substring` examples.
