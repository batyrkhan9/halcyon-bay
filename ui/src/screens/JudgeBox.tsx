import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, errorText } from '../api/client';
import { IconArrowRight } from '../components/icons';
import { Button, ErrorNote, Kbd, Page } from '../components/ui';

const EXAMPLES = [
  'Rosa Diaz came to the ER with a broken wrist. Family of three, she makes about $41,000 a year at a grocery store and brought two pay stubs. The bill is $6,200 and she has no insurance.',
  'Ahmed Karimi, 61, was admitted for two nights with chest pain. Lives alone, on Medi-Cal since March. His bill is $18,400.',
  'Lena Okoye, a single mom with two kids, gets CalFresh and has no pay stubs because she cleans houses for cash. Clinic visit, $1,350 bill.',
  'Daniel Price earns $142,000 a year, household of 2, pay stubs on file. Outpatient surgery bill of $4,800.',
];

export default function JudgeBox() {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const submit = async () => {
    if (!text.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.judgeBox(text.trim());
      navigate(`/accounts/${encodeURIComponent(r.data.account_id)}?live=1`);
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  };

  return (
    <Page eyebrow="Judge box" title="Describe a patient in plain English." lede="It becomes a new account in the billing office, and you watch the AI work it, step by step, under the same rules and the same gateway as everyone else.">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              void submit();
            }
          }}
          rows={6}
          autoFocus
          placeholder={EXAMPLES[0]}
          aria-label="Describe a patient"
          className="w-full resize-y rounded-3xl border border-line bg-surface px-8 py-7 text-[1.625rem] leading-[1.5] tracking-[-0.01em] text-ink shadow-lift outline-none transition focus:border-accent focus:ring-4 focus:ring-accent/10"
        />
        <div className="mt-6 flex flex-wrap items-center gap-5">
          <Button tone="primary" size="lg" type="submit" disabled={busy || !text.trim()}>
            {busy ? 'Opening the account…' : 'Work this patient'} <IconArrowRight size={20} />
          </Button>
          <span className="inline-flex items-center gap-1.5 text-[0.9375rem] text-ink3">
            or <Kbd>⌘</Kbd>
            <Kbd>Enter</Kbd>
          </span>
        </div>
        {error && (
          <div className="mt-5">
            <ErrorNote>{error}</ErrorNote>
          </div>
        )}
      </form>

      <div className="mt-16">
        <div className="mb-4 text-eyebrow font-semibold uppercase text-ink3">Or start from one of these</div>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              type="button"
              onClick={() => setText(ex)}
              className="rounded-2xl border border-line bg-surface px-6 py-5 text-left text-[1.0625rem] leading-relaxed text-ink2 transition hover:border-accent/40 hover:text-ink"
            >
              {ex}
            </button>
          ))}
        </div>
        <p className="mt-6 text-[0.9375rem] text-ink3">Everything here is synthetic. Please don't type a real person's details.</p>
      </div>
    </Page>
  );
}
