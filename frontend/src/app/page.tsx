"use client";

import Image from "next/image";
import { FormEvent, useEffect, useMemo, useState } from "react";

// Use same-origin /api routes; Next.js proxies them in development and Nginx in deployment.
const API = process.env.NEXT_PUBLIC_API_URL ?? "";

type Overview = { students: number; topics: number; topic_names: string[]; summary_file: string };
type TopicScore = {
  topic: string; tests_attempted: number; total_questions: number; total_correct: number;
  weighted_score: number; max_score: number; score_pct: number; level: string; confidence: string;
};
type Profile = {
  user_id: number; overall_score_pct: number; overall_level: string; confidence: string;
  questions_seen: number; topics: TopicScore[];
};
type Placement = {
  topic: string; student_score_pct: number; percentile: number; cohort_size: number;
  placement_label: string; peers: { user_id: number; full_name: string; score_pct: number; difference: number }[];
};
type AccountChoice = { user_id: number; full_name: string };
type TopicRecommendation = {
  topic: string; kind: "similar_students" | "popular_fallback"; similar_students_count?: number;
  similarity_weight?: number; students_count?: number; peer_average_pct: number; reason: string;
};
type ChapterRecommendation = { chapter: string; test_date: string; total_questions: number; score_pct: number; reason: string };
type RecommendationResponse = {
  topic_recommendations: TopicRecommendation[];
  recommendation_basis: string;
  similar_students_used: number;
  chapter_recommendations: ChapterRecommendation[];
  chapter_test_date: string | null;
  chapter_message: string | null;
};

class ApiError extends Error {
  status: number;
  payload: { detail?: string | { message?: string; accounts?: AccountChoice[] } };

  constructor(status: number, payload: { detail?: string | { message?: string; accounts?: AccountChoice[] } }) {
    const detail = payload.detail;
    super(typeof detail === "string" ? detail : detail?.message ?? "The request could not be completed.");
    this.status = status;
    this.payload = payload;
  }
}

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API}${path}`, { cache: "no-store" });
  const data = await response.json();
  if (!response.ok) throw new ApiError(response.status, data);
  return data as T;
}

function scoreClass(score: number): string {
  if (score >= 80) return "score-high";
  if (score >= 60) return "score-mid";
  return "score-low";
}

export default function Home() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [studentInput, setStudentInput] = useState("");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [recommendations, setRecommendations] = useState<TopicRecommendation[]>([]);
  const [chapterRecommendations, setChapterRecommendations] = useState<ChapterRecommendation[]>([]);
  const [chapterMessage, setChapterMessage] = useState<string | null>(null);
  const [chapterTestDate, setChapterTestDate] = useState<string | null>(null);
  const [placement, setPlacement] = useState<Placement | null>(null);
  const [selectedTopic, setSelectedTopic] = useState("");
  const [accountChoices, setAccountChoices] = useState<AccountChoice[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    request<{ data_ready: boolean; detail?: string }>("/api/health")
      .then(async (health) => {
        setReady(health.data_ready);
        if (health.data_ready) setOverview(await request<Overview>("/api/overview"));
        else setError(health.detail ?? "Prepared data is not available yet.");
      })
      .catch((cause: Error) => setError(cause.message));
  }, []);

  const activeTopic = useMemo(
    () => profile?.topics.find((item) => item.topic === selectedTopic) ?? profile?.topics[0],
    [profile, selectedTopic],
  );
  const activeUserId = profile?.user_id;
  const activeTopicName = activeTopic?.topic;

  useEffect(() => {
    if (!activeUserId || !activeTopicName) return;
    const userId = activeUserId;
    request<Placement>(`/api/students/${userId}/placement?topic=${encodeURIComponent(activeTopicName)}`)
      .then(setPlacement).catch(() => setPlacement(null));
    request<RecommendationResponse>(`/api/students/${userId}/recommendations?topic=${encodeURIComponent(activeTopicName)}`)
      .then((result) => {
        setRecommendations(result.topic_recommendations);
        setChapterRecommendations(result.chapter_recommendations);
        setChapterMessage(result.chapter_message);
        setChapterTestDate(result.chapter_test_date);
      })
      .catch(() => {
        setRecommendations([]);
        setChapterRecommendations([]);
        setChapterMessage("Recommendations could not be loaded.");
        setChapterTestDate(null);
      });
  }, [activeUserId, activeTopicName]);

  async function loadStudent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!studentInput.trim()) return;
    setLoading(true);
    setError("");
    setAccountChoices([]);
    setProfile(null);
    setPlacement(null);
    try {
      const student = await request<Profile>(`/api/students/lookup?email=${encodeURIComponent(studentInput.trim())}`);
      showProfile(student);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409 && typeof cause.payload.detail === "object") {
        setAccountChoices(cause.payload.detail.accounts ?? []);
      }
      setError(cause instanceof Error ? cause.message : "Unable to load student profile.");
    } finally {
      setLoading(false);
    }
  }

  function showProfile(student: Profile) {
    setProfile(student);
    setSelectedTopic(student.topics[0]?.topic ?? "");
    setRecommendations([]);
    setChapterRecommendations([]);
    setChapterMessage(null);
    setChapterTestDate(null);
  }

  async function chooseAccount(userId: number) {
    setLoading(true);
    setError("");
    setAccountChoices([]);
    setProfile(null);
    setPlacement(null);
    try {
      showProfile(await request<Profile>(`/api/students/${userId}`));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load student profile.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand-mark">CA</div>
        <div className="brand-copy"><strong>Capability</strong><span>STUDENT INSIGHTS</span></div>
        <div className="side-rule" />
        <div className="nav-item nav-active"><span className="nav-icon">◫</span> Overview</div>
        <div className="sidebar-note"><span className="pulse-dot" /> Complexity-aware scoring</div>
        <div className="sidebar-bottom"><Image className="aroha-logo" src="/aroha-logo.png" alt="Aroha Technologies" width={64} height={24} unoptimized /><div><strong>Analysis workspace</strong><small>Private cohort view</small></div></div>
      </aside>

      <section className="main-area">
        <header className="topbar">
          <div className="breadcrumb">Workspace <span>/</span> <b>Capability overview</b></div>
          <div className="top-status"><span className={`status-dot ${ready ? "online" : "offline"}`} />{ready ? "Dataset connected" : "Waiting for prepared data"}</div>
        </header>

        <div className="content">
          <section className="welcome-row">
            <div><p className="eyebrow">STUDENT PERFORMANCE INTELLIGENCE</p><h1>Capability overview</h1><p className="subheading">A clearer view of demonstrated skill, question complexity, and next steps.</p></div>
            <div className="date-chip"><span className="calendar-icon">▦</span> Weighted by question complexity</div>
          </section>

          {!ready && <section className="notice notice-warn"><div className="notice-icon">!</div><div><strong>Prepare the dataset to get started</strong><p>{error || "The API is running, but no processed summary has been generated."} Run the preparation command in the project guide, then restart the API.</p></div></section>}
          {error && ready && <section className="notice notice-error"><div className="notice-icon">!</div><div><strong>{accountChoices.length ? "Choose the student account" : "Could not load student"}</strong><p>{error}</p>{accountChoices.map((account) => <button className="account-choice" key={account.user_id} onClick={() => chooseAccount(account.user_id)} disabled={loading}><span>{account.full_name}</span><small>Student ID {account.user_id}</small><b>View profile →</b></button>)}</div></section>}

          <section className="stat-grid">
            <article className="stat-card"><div className="stat-top"><span>STUDENTS IN COHORT</span><span className="stat-icon indigo">♙</span></div><strong>{overview?.students.toLocaleString() ?? "—"}</strong><small>Unique learners in prepared data</small></article>
            <article className="stat-card"><div className="stat-top"><span>ASSESSMENT TOPICS</span><span className="stat-icon mint">◈</span></div><strong>{overview?.topics ?? "—"}</strong><small>Topics available for comparison</small></article>
            <article className="stat-card"><div className="stat-top"><span>SCORING MODEL</span><span className="stat-icon amber">↗</span></div><strong className="model-value">Complexity weighted</strong><small>Correct answers weighted by level</small></article>
          </section>

          <section className="panel lookup-panel">
            <div className="panel-heading"><div><p className="eyebrow">INDIVIDUAL ANALYSIS</p><h2>Explore a student profile</h2></div><span className="lock-badge">Email lookup</span></div>
            <form className="lookup-form" onSubmit={loadStudent}><label htmlFor="student-email">Student email</label><div className="input-row"><input id="student-email" type="email" autoComplete="email" value={studentInput} onChange={(event) => setStudentInput(event.target.value)} placeholder="Enter the student's email address" disabled={!ready} required /><button type="submit" disabled={!ready || loading}>{loading ? <><span className="spinner" /> Loading</> : <>View profile <span>→</span></>}</button></div><small>Results are provisional for students with limited answered questions. Email is used only for lookup.</small></form>
          </section>

          {profile && <>
            <section className="profile-heading"><div className="profile-avatar">{String(profile.user_id).slice(-2)}</div><div className="profile-title"><span>STUDENT PROFILE · ID {profile.user_id}</span><h2>Capability snapshot</h2></div><div className={`confidence-pill confidence-${profile.confidence}`}>{profile.confidence} evidence</div></section>
            <section className="profile-grid">
              <article className="panel overall-card"><div className="panel-heading"><div><p className="eyebrow">OVERALL PERFORMANCE</p><h2>Weighted score</h2></div><span className={`level-pill ${scoreClass(profile.overall_score_pct)}`}>{profile.overall_level}</span></div><div className="big-score">{profile.overall_score_pct}<span>%</span></div><div className="meter"><div className={`meter-fill ${scoreClass(profile.overall_score_pct)}`} style={{ width: `${Math.min(profile.overall_score_pct, 100)}%` }} /></div><div className="score-foot"><span>Across {profile.topics.length} topic{profile.topics.length === 1 ? "" : "s"}</span><span>{profile.questions_seen} questions seen</span></div><div className="method-note">Points are weighted 1 / 2 / 3 for beginner, intermediate, and expert questions, then normalized by the available weighted points.</div></article>
              <article className="panel placement-card"><div className="panel-heading"><div><p className="eyebrow">COHORT PLACEMENT</p><h2>Similar capability</h2></div><span className="target-icon">◎</span></div><label className="select-label" htmlFor="topic-select">Compare by topic</label><select id="topic-select" value={activeTopic?.topic ?? ""} onChange={(event) => setSelectedTopic(event.target.value)}>{profile.topics.map((topic) => <option key={topic.topic} value={topic.topic}>{topic.topic}</option>)}</select>{placement ? <><div className="placement-number">{placement.percentile}<span>th</span></div><p className="placement-caption">percentile in <b>{placement.topic}</b> · cohort of {placement.cohort_size}</p><div className="peer-list"><div className="peer-legend"><span>SIMILAR STUDENT</span><span>SCORE</span><span>VS YOU</span></div>{placement.peers.slice(0, 3).map((peer) => <div className="peer-row" key={peer.user_id}><span className="peer-avatar">{peer.full_name.split(/\s+/).map((part) => part[0]).slice(0, 2).join("").toUpperCase()}</span><span className="peer-name"><b>{peer.full_name}</b><small>ID {peer.user_id}</small></span><span className="peer-score">{peer.score_pct}%</span><span className={`peer-diff ${peer.difference >= 0 ? "positive" : "negative"}`}>{peer.difference > 0 ? "+" : ""}{peer.difference.toFixed(2)} pp</span></div>)}{placement.peers.length === 0 && <p className="empty-inline">No other students in this topic cohort.</p>}</div></> : <div className="loading-placeholder">Calculating cohort comparison…</div>}</article>
            </section>

            <section className="lower-grid">
              <article className="panel topic-panel"><div className="panel-heading"><div><p className="eyebrow">TOPIC BREAKDOWN</p><h2>Where capability shows up</h2></div><span className="muted-count">{profile.topics.length} topics</span></div><div className="topic-table"><div className="table-head"><span>TOPIC</span><span>QUESTIONS</span><span>TESTS</span><span>SCORE</span></div>{profile.topics.map((topic) => <div className="table-row" key={topic.topic}><div className="topic-name"><span className="topic-dot" />{topic.topic}<small>{topic.level} · {topic.confidence} evidence</small></div><span>{topic.total_questions}</span><span>{topic.tests_attempted}</span><div className="topic-score"><div className="mini-meter"><span style={{ width: `${Math.min(topic.score_pct, 100)}%` }} /></div><b>{topic.score_pct}%</b></div></div>)}</div></article>
              <article className="panel recommendations-panel"><div className="panel-heading"><div><p className="eyebrow">SUGGESTED NEXT STEPS</p><h2>Recommended topics</h2></div><span className="sparkle">✦</span></div><p className="recommend-intro">Topics not yet attempted, ranked from similar students’ assessment histories. General-popularity suggestions are used when peer evidence is sparse.</p>{recommendations.length ? <div className="recommend-list">{recommendations.map((item, index) => <div className="recommend-item" key={`${item.kind}-${item.topic}`}><span className={`recommend-number ${item.kind}`}>{String(index + 1).padStart(2, "0")}</span><div><strong>{item.topic}<span className={`recommend-tag ${item.kind}`}>{item.kind === "similar_students" ? "SIMILAR STUDENTS" : "POPULAR FALLBACK"}</span></strong><p>{item.reason}</p></div></div>)}</div> : <div className="empty-recommend"><span>✓</span><p>No unattempted topics are available to recommend.</p></div>}<div className="chapter-recommendations"><div className="chapter-heading"><div><p className="eyebrow">LATEST TEST REVIEW</p><h3>Chapters to focus on{activeTopicName ? ` · ${activeTopicName}` : ""}</h3></div>{chapterTestDate && <span className="chapter-date">{chapterTestDate}</span>}</div>{chapterRecommendations.length ? chapterRecommendations.map((item) => <div className="chapter-item" key={item.chapter}><span className="chapter-score">{item.score_pct}%</span><div><strong>{item.chapter}</strong><small>{item.total_questions} questions · {item.reason}</small></div></div>) : <p className="chapter-empty">{chapterMessage ?? "Select a topic to see chapter-level feedback from the latest test."}</p>}</div><div className="recommend-disclaimer">These are history-based suggestions, not predicted outcomes.</div></article>
            </section>
          </>}
        </div>
      </section>
    </main>
  );
}
