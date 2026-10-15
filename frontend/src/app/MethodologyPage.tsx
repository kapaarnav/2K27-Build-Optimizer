export function MethodologyPage() {
  return (
    <article className="space-y-6">
      <header className="space-y-3">
        <h1 className="text-3xl font-semibold tracking-tight">Methodology</h1>
        <p className="text-stone-700">
          This is an unofficial planning tool. A recommendation is shown only when the
          rules needed to recreate it have been checked against the builder.
        </p>
      </header>
      <section className="space-y-2">
        <h2 className="text-xl font-semibold">What the statuses mean</h2>
        <ul className="list-disc space-y-2 pl-5 text-stone-800">
          <li>Unsupported means the verified rules do not cover the request.</li>
          <li>Infeasible means the request breaks a verified game rule or an exact requirement.</li>
          <li>Not found within time means the search ended before it could prove a result.</li>
        </ul>
      </section>
      <section className="space-y-2">
        <h2 className="text-xl font-semibold">Grades</h2>
        <p className="text-stone-700">
          A score from 0 to 100 describes how well a build fits the request you submitted.
          The breakdown lists the pieces of that score. A high score is a strong fit for
          those inputs, and it is a personal fit rather than a universal MyPLAYER ranking.
        </p>
      </section>
      <section className="space-y-2">
        <h2 className="text-xl font-semibold">Time limit</h2>
        <p className="text-stone-700">
          The search stops at a fixed time budget. A partial result lists builds that
          passed the rules check and says the ranking is unproven. A proven result says
          the ranking was proved for the supported bodies.
        </p>
      </section>
      <section className="space-y-2">
        <h2 className="text-xl font-semibold">This revision</h2>
        <p className="text-stone-700">
          The active ruleset has no verified coverage. Generate will not return a build,
          a grade, or an archetype name until that coverage exists. A missing rule is not
          treated as an impossible build.
        </p>
      </section>
    </article>
  );
}
