"use client";

import { useState } from "react";

import type { Certification, Publication } from "@/lib/types/resume";
import styles from "./CredentialsEditor.module.css";

interface CredentialsEditorProps {
  certifications: Certification[];
  publications: Publication[];
  /** Re-reads the stored profile once a save has landed. */
  onSaved?: () => void | Promise<void>;
}

type Draft<T> = T & { _key: string };

const nextKey = () => Math.random().toString(36).slice(2);

function emptyCertification(): Draft<Certification> {
  return {
    _key: nextKey(),
    name: "",
    issuer: null,
    date: null,
    expiry: null,
    credential_id: null,
  };
}

function emptyPublication(): Draft<Publication> {
  return {
    _key: nextKey(),
    title: "",
    publisher: null,
    date: null,
    url: null,
    description: null,
  };
}

/** Empty strings from a text input mean "not set", not "" — the API takes null. */
const orNull = (value: string) => (value.trim() ? value.trim() : null);

const withKeys = <T,>(entries: T[]): Draft<T>[] =>
  entries.map((entry) => ({ ...entry, _key: nextKey() }));

// The render key is local bookkeeping and never leaves the component.
const stripKeys = <T,>(drafts: Draft<T>[]): T[] =>
  drafts.map((draft) => {
    const entry = { ...draft } as Draft<T>;
    delete (entry as { _key?: string })._key;
    return entry as T;
  });

/**
 * The profile's hand-kept sections. These are the two a person keeps adding to
 * between resume uploads — a certification finished this week is in no PDF —
 * so they are editable here at any time, and a later re-parse merges into them
 * rather than replacing them.
 */
export default function CredentialsEditor({
  certifications,
  publications,
  onSaved,
}: CredentialsEditorProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [certDrafts, setCertDrafts] = useState<Draft<Certification>[]>([]);
  const [pubDrafts, setPubDrafts] = useState<Draft<Publication>[]>([]);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  function startEditing() {
    setCertDrafts(withKeys(certifications));
    setPubDrafts(withKeys(publications));
    setError(null);
    setNote(null);
    setIsEditing(true);
  }

  function cancelEditing() {
    setIsEditing(false);
    setError(null);
  }

  function updateCert(key: string, field: keyof Certification, value: string) {
    setCertDrafts((drafts) =>
      drafts.map((d) =>
        d._key === key ? { ...d, [field]: field === "name" ? value : orNull(value) } : d,
      ),
    );
  }

  function updatePub(key: string, field: keyof Publication, value: string) {
    setPubDrafts((drafts) =>
      drafts.map((d) =>
        d._key === key ? { ...d, [field]: field === "title" ? value : orNull(value) } : d,
      ),
    );
  }

  async function handleSave() {
    const certs = stripKeys(certDrafts)
      .map((c) => ({ ...c, name: c.name.trim() }))
      .filter((c) => c.name);
    const pubs = stripKeys(pubDrafts)
      .map((p) => ({ ...p, title: p.title.trim() }))
      .filter((p) => p.title);

    // A row left blank is an abandoned "Add", not a deletion of everything
    // else — but a row the user typed a name into and then emptied would
    // vanish without a word, so say so instead of dropping it silently.
    if (certs.length !== certDrafts.length || pubs.length !== pubDrafts.length) {
      setError("Every entry needs a name before it can be saved.");
      return;
    }

    setIsSaving(true);
    setError(null);
    setNote(null);

    try {
      const res = await fetch("/api/profile/edit", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ certifications: certs, publications: pubs }),
      });
      const data = await res.json().catch(() => null);

      if (!res.ok || !data?.success) {
        setError(data?.message ?? "Could not save your changes.");
        return;
      }

      setIsEditing(false);
      setNote(data.message ?? "Saved.");
      await onSaved?.();
    } catch {
      setError("Could not reach the server. Please try again.");
    } finally {
      setIsSaving(false);
    }
  }

  const isEmpty = certifications.length === 0 && publications.length === 0;

  return (
    <section className={styles.section}>
      <div className={styles.sectionHeader}>
        <h2 className={styles.sectionTitle}>Certifications &amp; Publications</h2>
        {!isEditing && (
          <button type="button" className={styles.actionBtn} onClick={startEditing}>
            {isEmpty ? "Add entries" : "Edit"}
          </button>
        )}
      </div>

      {note && !isEditing && (
        <p className={styles.note} role="status">
          {note}
        </p>
      )}

      {!isEditing && isEmpty && (
        <p className={styles.emptyPrompt}>
          Nothing here yet. Certifications and publications you add stay on your
          profile — uploading a new resume will not remove them.
        </p>
      )}

      {!isEditing && !isEmpty && (
        <>
          {certifications.length > 0 && (
            <div className={styles.group}>
              <h3 className={styles.groupTitle}>Certifications</h3>
              <div className={styles.entryList}>
                {certifications.map((cert, i) => (
                  <div key={i} className={styles.entry}>
                    <p className={styles.entryTitle}>{cert.name}</p>
                    <p className={styles.entryOrg}>
                      {[cert.issuer, cert.date].filter(Boolean).join(" · ")}
                      {cert.credential_id ? ` · ID: ${cert.credential_id}` : ""}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {publications.length > 0 && (
            <div className={styles.group}>
              <h3 className={styles.groupTitle}>Publications</h3>
              <div className={styles.entryList}>
                {publications.map((pub, i) => (
                  <div key={i} className={styles.entry}>
                    <div className={styles.entryHeader}>
                      <p className={styles.entryTitle}>{pub.title}</p>
                      {pub.date && <span className={styles.entryDate}>{pub.date}</span>}
                    </div>
                    {pub.publisher && <p className={styles.entryOrg}>{pub.publisher}</p>}
                    {pub.description && <p className={styles.entryDesc}>{pub.description}</p>}
                    {pub.url && (
                      <a
                        href={pub.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={styles.link}
                      >
                        View publication
                      </a>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {isEditing && (
        <div className={styles.editor}>
          <div className={styles.group}>
            <h3 className={styles.groupTitle}>Certifications</h3>
            {certDrafts.map((cert) => (
              <div key={cert._key} className={styles.editRow}>
                <div className={styles.fields}>
                  <input
                    className={styles.input}
                    placeholder="Certification name"
                    aria-label="Certification name"
                    value={cert.name ?? ""}
                    onChange={(e) => updateCert(cert._key, "name", e.target.value)}
                  />
                  <input
                    className={styles.input}
                    placeholder="Issuer"
                    aria-label="Issuer"
                    value={cert.issuer ?? ""}
                    onChange={(e) => updateCert(cert._key, "issuer", e.target.value)}
                  />
                  <input
                    className={styles.inputNarrow}
                    placeholder="Date"
                    aria-label="Date"
                    value={cert.date ?? ""}
                    onChange={(e) => updateCert(cert._key, "date", e.target.value)}
                  />
                  <input
                    className={styles.inputNarrow}
                    placeholder="Credential ID"
                    aria-label="Credential ID"
                    value={cert.credential_id ?? ""}
                    onChange={(e) => updateCert(cert._key, "credential_id", e.target.value)}
                  />
                </div>
                <button
                  type="button"
                  className={styles.removeBtn}
                  aria-label={`Remove ${cert.name || "certification"}`}
                  onClick={() =>
                    setCertDrafts((drafts) => drafts.filter((d) => d._key !== cert._key))
                  }
                >
                  Remove
                </button>
              </div>
            ))}
            <button
              type="button"
              className={styles.addBtn}
              onClick={() => setCertDrafts((drafts) => [...drafts, emptyCertification()])}
            >
              + Add certification
            </button>
          </div>

          <div className={styles.group}>
            <h3 className={styles.groupTitle}>Publications</h3>
            {pubDrafts.map((pub) => (
              <div key={pub._key} className={styles.editRow}>
                <div className={styles.fields}>
                  <input
                    className={styles.input}
                    placeholder="Publication title"
                    aria-label="Publication title"
                    value={pub.title ?? ""}
                    onChange={(e) => updatePub(pub._key, "title", e.target.value)}
                  />
                  <input
                    className={styles.input}
                    placeholder="Publisher"
                    aria-label="Publisher"
                    value={pub.publisher ?? ""}
                    onChange={(e) => updatePub(pub._key, "publisher", e.target.value)}
                  />
                  <input
                    className={styles.inputNarrow}
                    placeholder="Date"
                    aria-label="Publication date"
                    value={pub.date ?? ""}
                    onChange={(e) => updatePub(pub._key, "date", e.target.value)}
                  />
                  <input
                    className={styles.input}
                    placeholder="Link"
                    aria-label="Publication link"
                    value={pub.url ?? ""}
                    onChange={(e) => updatePub(pub._key, "url", e.target.value)}
                  />
                  <textarea
                    className={styles.textarea}
                    placeholder="Short description (optional)"
                    aria-label="Publication description"
                    rows={2}
                    value={pub.description ?? ""}
                    onChange={(e) => updatePub(pub._key, "description", e.target.value)}
                  />
                </div>
                <button
                  type="button"
                  className={styles.removeBtn}
                  aria-label={`Remove ${pub.title || "publication"}`}
                  onClick={() =>
                    setPubDrafts((drafts) => drafts.filter((d) => d._key !== pub._key))
                  }
                >
                  Remove
                </button>
              </div>
            ))}
            <button
              type="button"
              className={styles.addBtn}
              onClick={() => setPubDrafts((drafts) => [...drafts, emptyPublication()])}
            >
              + Add publication
            </button>
          </div>

          {error && (
            <p className={styles.error} role="alert">
              {error}
            </p>
          )}

          <div className={styles.editorActions}>
            <button
              type="button"
              className={styles.saveBtn}
              onClick={handleSave}
              disabled={isSaving}
            >
              {isSaving ? "Saving…" : "Save changes"}
            </button>
            <button
              type="button"
              className={styles.actionBtn}
              onClick={cancelEditing}
              disabled={isSaving}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
