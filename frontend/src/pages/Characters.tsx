import { useEffect, useState, type FormEvent } from "react";

import { ApiError, api } from "../api";
import type { Character } from "../types";
import { predicateLabel } from "./Contradictions";
import { useWorkspace } from "./workspaceContext";

// Canon attributes the contradiction checks understand. Other keys are stored but not checked.
const CHECKED_ATTRIBUTES = ["eye_color", "hair_color", "handedness", "birthplace"];

interface Form {
  name: string;
  aliases: string;
  description: string;
  attributes: [string, string][];
}

const emptyForm: Form = { name: "", aliases: "", description: "", attributes: [] };

const toForm = (c: Character): Form => ({
  name: c.name,
  aliases: c.aliases.join(", "),
  description: c.description,
  attributes: Object.entries(c.attributes),
});

const fromForm = (f: Form) => ({
  name: f.name.trim(),
  aliases: f.aliases
    .split(",")
    .map((a) => a.trim())
    .filter(Boolean),
  description: f.description,
  attributes: Object.fromEntries(
    f.attributes.filter(([k, v]) => k.trim() && v.trim()).map(([k, v]) => [k.trim(), v.trim()]),
  ),
});

function CharacterForm({
  initial,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial: Form;
  submitLabel: string;
  onSubmit: (f: Form) => Promise<void>;
  onCancel?: () => void;
}) {
  const [form, setForm] = useState<Form>(initial);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await onSubmit(form);
      if (!onCancel) setForm(emptyForm);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const setAttr = (i: number, pos: 0 | 1, value: string) =>
    setForm({
      ...form,
      attributes: form.attributes.map((a, j) =>
        j === i ? ((pos === 0 ? [value, a[1]] : [a[0], value]) as [string, string]) : a,
      ),
    });

  return (
    <form onSubmit={submit} className="character-form">
      <label>
        Name
        <input
          aria-label="Character name"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
      </label>
      <label>
        Aliases <span className="muted small">(comma-separated; first name is implied)</span>
        <input
          aria-label="Aliases"
          value={form.aliases}
          placeholder="the Warden, Corr"
          onChange={(e) => setForm({ ...form, aliases: e.target.value })}
        />
      </label>
      <label>
        Description
        <textarea
          aria-label="Description"
          rows={2}
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
        />
      </label>
      <fieldset>
        <legend>Canon (character sheet)</legend>
        {form.attributes.map(([k, v], i) => (
          <div className="attr-row" key={i}>
            <select
              aria-label="Attribute"
              value={CHECKED_ATTRIBUTES.includes(k) ? k : "__custom"}
              onChange={(e) => setAttr(i, 0, e.target.value === "__custom" ? "" : e.target.value)}
            >
              {CHECKED_ATTRIBUTES.map((a) => (
                <option key={a} value={a}>
                  {predicateLabel(a)}
                </option>
              ))}
              <option value="__custom">other…</option>
            </select>
            {!CHECKED_ATTRIBUTES.includes(k) && (
              <input
                aria-label="Attribute key"
                placeholder="snake_case_key"
                value={k}
                onChange={(e) => setAttr(i, 0, e.target.value)}
              />
            )}
            <input
              aria-label="Attribute value"
              value={v}
              onChange={(e) => setAttr(i, 1, e.target.value)}
            />
            <button
              type="button"
              className="ghost small"
              onClick={() =>
                setForm({ ...form, attributes: form.attributes.filter((_, j) => j !== i) })
              }
            >
              Remove
            </button>
          </div>
        ))}
        <button
          type="button"
          className="ghost small"
          onClick={() =>
            setForm({
              ...form,
              attributes: [
                ...form.attributes,
                [
                  CHECKED_ATTRIBUTES.find((a) => !form.attributes.some(([k]) => k === a)) ??
                    "",
                  "",
                ],
              ],
            })
          }
        >
          + Add fact
        </button>
      </fieldset>
      {error && <p className="error">{error}</p>}
      <div className="form-actions">
        <button type="submit" disabled={!form.name.trim()}>
          {submitLabel}
        </button>
        {onCancel && (
          <button type="button" className="ghost" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}

export default function Characters() {
  const { novel } = useWorkspace();
  const [characters, setCharacters] = useState<Character[] | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    api.listCharacters(novel.id).then(setCharacters).catch((e: Error) => setError(e.message));

  useEffect(() => {
    load();
  }, [novel.id]);

  const update = async (c: Character, f: Form) => {
    try {
      await api.updateCharacter(c.id, c.version, fromForm(f));
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        await load();
        throw new Error(`${e.message} The latest version is now shown; edit again.`);
      }
      throw e;
    }
    setEditing(null);
    await load();
  };

  const remove = async (c: Character) => {
    if (!window.confirm(`Delete ${c.name}? Facts extracted about them are removed too.`)) return;
    await api.deleteCharacter(c.id);
    await load();
  };

  return (
    <div className="page">
      <h1>Characters</h1>
      <p className="muted small">
        Names and aliases decide which text the extractor attributes to whom. Canon facts on
        the sheet are what the contradiction report checks the text against.
      </p>
      {error && <p className="error">{error}</p>}
      <ul className="card-list">
        {characters?.map((c) =>
          editing === c.id ? (
            <li key={c.id} className="card" data-testid="character-editor">
              <CharacterForm
                initial={toForm(c)}
                submitLabel="Save"
                onSubmit={(f) => update(c, f)}
                onCancel={() => setEditing(null)}
              />
            </li>
          ) : (
            <li key={c.id} className="card" data-testid="character-card">
              <div className="row">
                <div>
                  <div className="card-title">{c.name}</div>
                  {c.aliases.length > 0 && (
                    <div className="muted small">also: {c.aliases.join(", ")}</div>
                  )}
                </div>
                <div className="actions">
                  <button className="ghost" onClick={() => setEditing(c.id)}>
                    Edit
                  </button>
                  <button className="ghost danger" onClick={() => remove(c)}>
                    Delete
                  </button>
                </div>
              </div>
              {c.description && <p>{c.description}</p>}
              {Object.keys(c.attributes).length > 0 && (
                <dl className="attrs">
                  {Object.entries(c.attributes).map(([k, v]) => (
                    <div key={k}>
                      <dt>{predicateLabel(k)}</dt>
                      <dd>{v}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </li>
          ),
        )}
      </ul>
      <section className="panel">
        <h2>New character</h2>
        <CharacterForm
          initial={emptyForm}
          submitLabel="Add character"
          onSubmit={async (f) => {
            await api.createCharacter(novel.id, fromForm(f));
            await load();
          }}
        />
      </section>
    </div>
  );
}
