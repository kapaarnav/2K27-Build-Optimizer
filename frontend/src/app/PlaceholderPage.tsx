type PlaceholderPageProps = {
  title: string;
  body: string;
};

export function PlaceholderPage({ title, body }: PlaceholderPageProps) {
  return (
    <section className="space-y-3">
      <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
      <p className="text-stone-700">{body}</p>
    </section>
  );
}
