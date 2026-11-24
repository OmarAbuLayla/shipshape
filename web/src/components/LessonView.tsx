import { Link } from "react-router-dom";

import { api } from "../lib/api";
import { useLoad } from "../lib/hooks";
import { Markdown } from "../lib/markdown";

/** One concept lesson, loaded by slug, concept or check id. */
export function LessonView({ name, compact = false }: { name: string; compact?: boolean }) {
  const lesson = useLoad(() => api.lesson(name), [name]);
  if (lesson.error) return <p className="muted">{lesson.error}</p>;
  if (!lesson.data) return <p className="faint">Loading the lesson…</p>;
  const { concept, summary, body, checks, slug } = lesson.data;
  return (
    <article className={`lesson ${compact ? "compact" : ""}`}>
      <p className="eyebrow">Lesson</p>
      {compact ? <h2>{concept}</h2> : <h1>{concept}</h1>}
      <p className="lesson-summary">{summary}</p>
      <Markdown text={body} />
      <p className="faint lesson-meta">
        Taught by {checks.map((c, i) => <span key={c}>{i > 0 && ", "}<code>{c}</code></span>)}
        {compact && (
          <>
            {" · "}
            <Link to={`/lessons/${slug}`}>open as a page</Link>
          </>
        )}
      </p>
    </article>
  );
}
