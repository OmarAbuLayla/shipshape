import { Link, useParams } from "react-router-dom";

import { LessonView } from "../components/LessonView";
import { api } from "../lib/api";
import { useLoad } from "../lib/hooks";

/** All lessons, or one lesson when the URL names it. */
export function Lessons() {
  const { slug } = useParams();
  if (slug) {
    return (
      <div className="page lessons-page">
        <Link className="back" to="/lessons">← All lessons</Link>
        <LessonView name={slug} />
      </div>
    );
  }
  return <LessonIndex />;
}

function LessonIndex() {
  const lessons = useLoad(() => api.lessons(), []);
  return (
    <div className="page lessons-page">
      <p className="eyebrow">Lessons</p>
      <h1>The ideas behind every check</h1>
      <p className="muted lead">
        Every finding names the concept it teaches. Each lesson explains the idea in plain words, shows a small
        before and after, says why engineers care, and is honest about what Shipshape can and cannot detect.
      </p>
      {lessons.error && <div className="form-error">{lessons.error}</div>}
      <div className="lesson-grid">
        {lessons.data?.map((lesson) => (
          <Link key={lesson.slug} className="card lesson-card" to={`/lessons/${lesson.slug}`}>
            <b>{lesson.concept}</b>
            <span>{lesson.summary}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
