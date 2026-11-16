import { SafetyNotice } from '../services/intake';

type Props = {
  noticeKey: string;
  notice: SafetyNotice;
  onDismiss: () => void;
  onCorrect: () => void;
};

const reasonCopy = {
  number: 'Information containing unverified numbers was not accepted.',
  percentage: 'Information containing unverified percentages was not accepted.',
  cost: 'Information containing unverified costs was not accepted.',
  date: 'Information containing unverified dates was not accepted.',
  word_quantity: 'Information containing unverified quantities written as words was not accepted.',
} as const;

export function SafetyDenialBanner({ noticeKey, notice, onDismiss, onCorrect }: Props) {
  return (
    <section
      className="safety-denial-banner"
      data-notice-key={noticeKey}
      role="alert"
      aria-labelledby={`safety-denial-title-${noticeKey}`}
      onKeyDown={(event) => {
        if (event.key === 'Escape' && event.target instanceof Node && event.currentTarget.contains(event.target)) {
          event.preventDefault();
          onDismiss();
        }
      }}
    >
      <div className="safety-denial-copy">
        <h2 id={`safety-denial-title-${noticeKey}`}>Some information was not accepted</h2>
        {notice.reasons.length ? (
          <ul>
            {notice.reasons.map((reason) => <li key={reason}>{reasonCopy[reason]}</li>)}
          </ul>
        ) : (
          <p>NoFacts rejected some information, but the detailed reason is unavailable.</p>
        )}
        <p>Please describe the idea without unsupported claims.</p>
      </div>
      <div className="safety-denial-actions">
        <button type="button" className="secondary-action" data-dismiss-action onClick={onDismiss}>Dismiss</button>
        <button type="button" className="primary-action" data-correction-action onClick={onCorrect}>Correct this input</button>
      </div>
    </section>
  );
}