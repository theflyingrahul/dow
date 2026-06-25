import { useEffect, useState } from 'react';
import { useStore } from '../../store/AppStore';
import { commitVersion, fetchSpec, saveSpec } from '../../data/loadData';
import { Button } from '../ui/Button';
import { IconCheck, IconSparkle } from '../ui/icons';

/**
 * Edit the working spec YAML and capture a version from the live server. Used
 * both in the empty-state Get-Started screen (firstRun) and the Edit-spec modal.
 * On a successful commit the page reloads so the freshly captured version (and
 * the full dashboard) render.
 */
export function SpecEditor({ firstRun = false }: { firstRun?: boolean }) {
  const { specName, specText } = useStore();
  const [text, setText] = useState(specText ?? '');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState<null | 'save' | 'commit'>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  // Re-seed from the server so the editor always reflects the file on disk
  // (it may have changed since the page loaded).
  useEffect(() => {
    let active = true;
    fetchSpec().then((s) => {
      if (active && s) setText(s.text);
    });
    return () => {
      active = false;
    };
  }, []);

  const onSave = async () => {
    setBusy('save');
    setError(null);
    setNote(null);
    const r = await saveSpec(text);
    setBusy(null);
    if (!r.ok) {
      setError(r.error || 'Could not save the spec.');
      return;
    }
    setNote(r.valid === false ? `Saved, but the YAML looks invalid: ${r.error}` : 'Spec saved.');
  };

  const onCommit = async () => {
    setBusy('commit');
    setError(null);
    setNote(null);
    const saved = await saveSpec(text);
    if (!saved.ok) {
      setBusy(null);
      setError(saved.error || 'Could not save the spec.');
      return;
    }
    const r = await commitVersion(message);
    if (!r.ok) {
      setBusy(null);
      setError(r.error || 'Commit failed.');
      return;
    }
    // Reload to pick up the new version and render the full dashboard.
    window.location.reload();
  };

  return (
    <div className="space-y-4">
      <div>
        <span className="kicker mb-1.5 block">
          Spec · <span className="font-mono text-ink-soft">specs/{specName}.yaml</span>
        </span>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          spellCheck={false}
          rows={firstRun ? 18 : 16}
          aria-label="Spec YAML"
          className="focus-ring w-full resize-y rounded-xl border border-border bg-surface px-3.5 py-3 font-mono text-xs leading-relaxed text-ink"
        />
      </div>

      <label className="block">
        <span className="kicker mb-1.5 block">Change note (optional)</span>
        <input
          type="text"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder={firstRun ? 'e.g. baseline' : 'e.g. lower temperature for steadier phrasing'}
          className="focus-ring h-11 w-full rounded-xl border border-border bg-surface px-3.5 text-sm text-ink placeholder:text-muted"
        />
      </label>

      {error && (
        <p className="rounded-xl border border-danger/30 bg-danger/10 px-3 py-2.5 text-2xs leading-relaxed text-danger-ink">
          {error}
        </p>
      )}
      {note && !error && (
        <p className="rounded-xl border border-border bg-surface-2/50 px-3 py-2.5 text-2xs leading-relaxed text-muted">
          {note}
        </p>
      )}

      <div className="flex items-center justify-end gap-2">
        <Button variant="ghost" type="button" onClick={onSave} disabled={busy !== null}>
          {busy === 'save' ? 'Saving…' : 'Save spec'}
        </Button>
        <Button
          variant="primary"
          type="button"
          onClick={onCommit}
          disabled={busy !== null}
          iconLeft={firstRun ? <IconSparkle className="h-4 w-4" /> : <IconCheck className="h-4 w-4" />}
        >
          {busy === 'commit'
            ? 'Capturing…'
            : firstRun
              ? 'Capture first version'
              : 'Capture version'}
        </Button>
      </div>
    </div>
  );
}
