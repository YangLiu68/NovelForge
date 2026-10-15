import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api";
import type { Novel } from "../types";

export default function NovelList() {
  const [novels, setNovels] = useState<Novel[] | null>(null);
  const [samples, setSamples] = useState<string[]>([]);
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  const load = () =>
    api.listNovels().then(setNovels).catch((e: Error) => setError(e.message));

  useEffect(() => {
    load();
    api.listSamples().then((s) => setSamples(s.map((x) => x.name))).catch(() => setSamples([]));
  }, []);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    try {
      const novel = await api.createNovel(title.trim());
      navigate(`/novels/${novel.id}`);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const importSample = async (name: string) => {
    setBusy(true);
    try {
      const res = await api.importSample(name);
      navigate(`/novels/${res.novel_id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (novel: Novel) => {
    if (!window.confirm(`Delete "${novel.title}" and all its chapters? This cannot be undone.`))
      return;
    await api.deleteNovel(novel.id);
    load();
  };

  return (
    <main className="page narrow">
      <h1>Your novels</h1>
      {error && <p className="error">{error}</p>}
      {novels === null ? (
        <p className="muted">Loading…</p>
      ) : novels.length === 0 ? (
        <p className="muted">No novels yet. Start one, or import the sample to look around.</p>
      ) : (
        <ul className="card-list">
          {novels.map((n) => (
            <li key={n.id} className="card row">
              <div>
                <Link to={`/novels/${n.id}`} className="card-title">
                  {n.title}
                </Link>
                <div className="muted small">
                  {n.chapter_count} chapters · {n.character_count} characters
                </div>
              </div>
              <button className="ghost danger" onClick={() => remove(n)}>
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}

      <section className="panel">
        <h2>New novel</h2>
        <form onSubmit={create} className="inline-form">
          <input
            aria-label="Novel title"
            placeholder="Title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <button type="submit" disabled={!title.trim()}>
            Create
          </button>
        </form>
      </section>

      {samples.length > 0 && (
        <section className="panel">
          <h2>Sample</h2>
          <p className="muted small">
            Three original chapters with seeded contradictions and labelled ground truth.
            Importing is idempotent.
          </p>
          {samples.map((s) => (
            <button key={s} onClick={() => importSample(s)} disabled={busy}>
              Import sample “{s}”
            </button>
          ))}
        </section>
      )}
    </main>
  );
}
